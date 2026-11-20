# One-motor test on ONE DFR0601 channel (set CHANNEL below); the other channel is held at 0 / low.
#   channel 1: P1 = GPIO 18, A1 = GPIO 8,  B1 = GPIO 9
#   channel 2: P2 = GPIO 10, A2 = GPIO 11, B2 = GPIO 12
# Forward: ramp to TEST_SPEED in 1 s, hold 1.5 s, ramp down 1 s, pause 1 s. Then the same in reverse.
# Every 0.25 s prints the encoder counts seen on GPIO 39 and GPIO 40 in that 0.25 s (+ totals).
# Channel 2 motor's encoder = GPIO 39 (confirmed 2026-11-20). Whole test is about 8.5 s.
# WHEEL OFF THE GROUND. Both channels go to 0 on any exit (finally).
from machine import Pin, PWM
import time

CHANNEL = 2          # 1 or 2: the channel under test
TEST_SPEED = 30      # percent (project maximum is 80; channel 2 ran fine at 30 and 80 on 2026-11-20)
TEST_SPEED = min(TEST_SPEED, 80)
RAMP_S = 1.0
HOLD_S = 1.5
PAUSE_S = 1.0
STEP_S = 0.05        # control step
PRINT_EVERY = 5      # steps -> 0.25 s

# Lift (MD10C) held OFF first: an unconfigured GPIO 14 floats, and on 2026-11-20 the lift ran together
# with channel 1 when this test left it floating. PWM GPIO 14 = 0, DIR GPIO 13 = 0.
lift_pwm = PWM(Pin(14), freq=1000, duty_u16=0)
lift_dir = Pin(13, Pin.OUT, value=0)

# Both channels low FIRST.
CH = {
    1: (PWM(Pin(18), freq=1000, duty_u16=0), Pin(8, Pin.OUT, value=0), Pin(9, Pin.OUT, value=0)),
    2: (PWM(Pin(10), freq=1000, duty_u16=0), Pin(11, Pin.OUT, value=0), Pin(12, Pin.OUT, value=0)),
}
if CHANNEL not in CH:
    raise ValueError("CHANNEL must be 1 or 2")
OTHER = 2 if CHANNEL == 1 else 1


def all_off():
    lift_pwm.duty_u16(0)
    lift_dir.value(0)
    for pwm, ina, inb in CH.values():
        pwm.duty_u16(0)
        ina.value(0)
        inb.value(0)


def set_test_channel(speed):
    # Same logic as follow_me.py: forward A=1 B=0, reverse A=0 B=1, 0 = both low.
    o_pwm, o_a, o_b = CH[OTHER]
    if o_pwm.duty_u16() != 0 or o_a.value() or o_b.value():
        all_off()
        raise RuntimeError("channel %d was not at 0" % OTHER)
    pwm, ina, inb = CH[CHANNEL]
    ina.value(1 if speed > 0 else 0)
    inb.value(1 if speed < 0 else 0)
    pwm.duty_u16(int(abs(speed) * 655))


def shown_speed():
    pwm, ina, inb = CH[CHANNEL]
    sign = 1 if ina.value() else -1 if inb.value() else 0
    return sign * (pwm.duty_u16() * 100 // 65535)


# --- Encoder counting on GPIO 39 and GPIO 40 ---
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

totals = {"fwd": [0, 0], "rev": [0, 0]}
t0 = time.ticks_ms()
step_no = 0


def run_phase(label, phase, target_fn, duration_s):
    """Run for duration_s, setting speed from target_fn(elapsed_s), printing every 0.25 s."""
    global step_no
    steps = int(duration_s / STEP_S + 0.5)
    for i in range(steps):
        set_test_channel(target_fn((i + 1) * STEP_S))
        time.sleep(STEP_S)
        step_no += 1
        if step_no % PRINT_EVERY == 0:
            a, b = take_counts()
            totals[phase][0] += a
            totals[phase][1] += b
            print("%5.2f s  %-12s speed %4d%%   GPIO39 %4d   GPIO40 %4d" % (
                time.ticks_diff(time.ticks_ms(), t0) / 1000, label, shown_speed(), a, b))


try:
    all_off()
    take_counts()  # clear
    print("Channel %d test: %d%% forward, then %d%% reverse. Channel %d held at 0." % (
        CHANNEL, TEST_SPEED, TEST_SPEED, OTHER))
    for phase, sign in (("fwd", 1), ("rev", -1)):
        name = "forward" if sign > 0 else "reverse"
        run_phase(name + " up", phase, lambda t: sign * TEST_SPEED * min(t / RAMP_S, 1), RAMP_S)
        run_phase(name + " hold", phase, lambda t: sign * TEST_SPEED, HOLD_S)
        run_phase(name + " down", phase, lambda t: sign * TEST_SPEED * max(1 - t / RAMP_S, 0), RAMP_S)
        run_phase("pause", phase, lambda t: 0, PAUSE_S if sign > 0 else 0.5)
    print("TOTAL forward: GPIO39 %d, GPIO40 %d" % tuple(totals["fwd"]))
    print("TOTAL reverse: GPIO39 %d, GPIO40 %d" % tuple(totals["rev"]))
finally:
    all_off()
    try:
        counters_off()
    except Exception:
        pass
    print("Motor stopped")
