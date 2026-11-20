# Tests the two DFR0601 channels ONE AT A TIME (never both at once):
#   channel 1: P1 = GPIO 18, A1 = GPIO 8,  B1 = GPIO 9
#   channel 2: P2 = GPIO 10, A2 = GPIO 11, B2 = GPIO 12
# Per channel: forward ramp to 30% in 0.5 s, hold 1 s, ramp down 0.5 s, pause 0.4 s, then the same
# in reverse. The idle channel is held at 0 / low. Every 0.25 s prints the encoder counts on GPIO 39
# and GPIO 40. Total about 9.6 s. WHEELS OFF THE GROUND. Everything goes to 0 on any exit (finally).
from machine import Pin, PWM
import time

# Lift (MD10C) held OFF first: an unconfigured GPIO 14 floats, and on 2026-11-20 the lift ran together
# with channel 1 when a wheel test left it floating. PWM GPIO 14 = 0, DIR GPIO 13 = 0.
lift_pwm = PWM(Pin(14), freq=1000, duty_u16=0)
lift_dir = Pin(13, Pin.OUT, value=0)

# Both channels low FIRST.
CH = {
    1: (PWM(Pin(18), freq=1000, duty_u16=0), Pin(8, Pin.OUT, value=0), Pin(9, Pin.OUT, value=0)),
    2: (PWM(Pin(10), freq=1000, duty_u16=0), Pin(11, Pin.OUT, value=0), Pin(12, Pin.OUT, value=0)),
}

TEST_SPEED = 30      # percent
RAMP_S = 0.5
HOLD_S = 1.0
PAUSE_S = 0.4
STEP_S = 0.05
PRINT_EVERY = 5      # steps -> 0.25 s


def all_off():
    lift_pwm.duty_u16(0)
    lift_dir.value(0)
    for pwm, ina, inb in CH.values():
        pwm.duty_u16(0)
        ina.value(0)
        inb.value(0)


def set_channel(ch, speed):
    # Same logic as follow_me.py: forward A=1 B=0, reverse A=0 B=1, 0 = both low.
    other_pwm, other_a, other_b = CH[2 if ch == 1 else 1]
    if other_pwm.duty_u16() != 0 or other_a.value() or other_b.value():
        all_off()
        raise RuntimeError("the other channel was not at 0")
    pwm, ina, inb = CH[ch]
    ina.value(1 if speed > 0 else 0)
    inb.value(1 if speed < 0 else 0)
    pwm.duty_u16(int(abs(speed) * 655))


def shown_speed(ch):
    pwm, ina, inb = CH[ch]
    sign = 1 if ina.value() else -1 if inb.value() else 0
    return sign * (pwm.duty_u16() * 100 // 65535)


# Encoder counting on GPIO 39 and GPIO 40.
pin39 = Pin(39, Pin.IN, Pin.PULL_UP)
pin40 = Pin(40, Pin.IN, Pin.PULL_UP)
try:
    from machine import Counter
    c39 = Counter(0, pin39, edge=Counter.RISING, filter_ns=10000)
    c40 = Counter(1, pin40, edge=Counter.RISING, filter_ns=10000)

    def take_counts():
        a, b = c39.value(), c40.value()
        c39.value(0)
        c40.value(0)
        return a, b

    def counters_off():
        c39.deinit()
        c40.deinit()

    print("Counting with machine.Counter (filter 10 us)")
except (ImportError, AttributeError, ValueError, TypeError) as e:
    print("machine.Counter not available (%r), using interrupts" % (e,))
    _n = [0, 0]

    def _irq39(p):
        _n[0] += 1

    def _irq40(p):
        _n[1] += 1

    pin39.irq(trigger=Pin.IRQ_RISING, handler=_irq39)
    pin40.irq(trigger=Pin.IRQ_RISING, handler=_irq40)

    def take_counts():
        a, b = _n[0], _n[1]
        _n[0] = 0
        _n[1] = 0
        return a, b

    def counters_off():
        pin39.irq(handler=None)
        pin40.irq(handler=None)

totals = {}
t0 = time.ticks_ms()
step_no = 0


def run_phase(ch, key, label, target_fn, duration_s):
    global step_no
    for i in range(int(duration_s / STEP_S + 0.5)):
        set_channel(ch, target_fn((i + 1) * STEP_S))
        time.sleep(STEP_S)
        step_no += 1
        if step_no % PRINT_EVERY == 0:
            a, b = take_counts()
            totals[key][0] += a
            totals[key][1] += b
            print("%5.2f s  CH%d %-12s speed %4d%%   GPIO39 %4d   GPIO40 %4d" % (
                time.ticks_diff(time.ticks_ms(), t0) / 1000, ch, label, shown_speed(ch), a, b))


try:
    all_off()
    take_counts()  # clear
    print("Testing channel 1, then channel 2, 30% forward and reverse each. Never both at once.")
    for ch in (1, 2):
        for sign in (1, -1):
            name = "fwd" if sign > 0 else "rev"
            key = "CH%d %s" % (ch, name)
            totals[key] = [0, 0]
            run_phase(ch, key, name + " up", lambda t: sign * TEST_SPEED * min(t / RAMP_S, 1), RAMP_S)
            run_phase(ch, key, name + " hold", lambda t: sign * TEST_SPEED, HOLD_S)
            run_phase(ch, key, name + " down", lambda t: sign * TEST_SPEED * max(1 - t / RAMP_S, 0), RAMP_S)
            run_phase(ch, key, "pause", lambda t: 0, PAUSE_S)
    for key in sorted(totals):
        print("TOTAL %s: GPIO39 %d, GPIO40 %d" % (key, totals[key][0], totals[key][1]))
finally:
    all_off()
    try:
        counters_off()
    except Exception:
        pass
    print("Motor stopped")
