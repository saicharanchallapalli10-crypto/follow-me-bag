"""lift_test_encoder.py - run the scissor lift motor and read its encoder at the same time

MicroPython on ESP32-S3. Run with `python3 tools/esp32.py run tests/lift_test_encoder.py`
(or from Thonny, interpreter: MicroPython (ESP32)).

Wiring (see the lift motor wiring page):
  GPIO 14 -> MD10C PWM      GPIO 13 -> MD10C DIR      ESP32 G -> MD10C GND
  Lift encoder A (yellow, through divider) -> GPIO 42
  Lift encoder B (white,  through divider) -> GPIO 38

What it does: runs the lift a short way in DIR 0, pauses, then back in
DIR 1. While it runs, it counts encoder A and encoder B separately every
0.1 s, so you can see each wire working. It stops on its own if encoder A
reads no pulses while powered (stall or wiring problem). Press Stop any time.

Start with the lift at mid-height so neither direction hits the end.
Note which DIR goes UP and set LIFT_UP_DIR in follow_me.py to match.
"""
from machine import Pin, PWM
import machine
import time

SPEED = 40          # lift power while moving (0-100). Keep it low for the first test
RUN_TIME = 1.0      # seconds to run each direction (after the ramp)
PAUSE = 1.5         # seconds to wait between directions
STALL_READS = 3     # this many 0.1 s readings with 0 pulses on A in a row = stalled
STALL_CHECK = True  # set False to test the motor even if encoder A isn't working
FILTER_NS = 10000   # ignore encoder pulses shorter than 10 microseconds

# ---------------- MD10C ----------------
pwm = PWM(Pin(14), freq=1000, duty_u16=0)
dir_pin = Pin(13, Pin.OUT, value=0)

# ---------------- Wheels: held OFF for this whole test ----------------
# (the wheel motors must never run while the lift runs)
for _p in (18, 10):
    PWM(Pin(_p), freq=1000, duty_u16=0)
for _p in (8, 9, 11, 12):
    Pin(_p, Pin.OUT, value=0)


def set_power(p):
    p = max(0, min(100, p))
    pwm.duty_u16(int(p * 655))


# ---------------- Lift encoder (A and B) ----------------
enc_a = Pin(42, Pin.IN, Pin.PULL_UP)
enc_b = Pin(38, Pin.IN, Pin.PULL_UP)

try:
    # Hardware counters 2 and 3 (the wheels use 0 and 1)
    from machine import Counter
    cnt_a = Counter(2, enc_a, edge=Counter.RISING, filter_ns=FILTER_NS)
    cnt_b = Counter(3, enc_b, edge=Counter.RISING, filter_ns=FILTER_NS)

    def read_counts():
        a = cnt_a.value()
        b = cnt_b.value()
        cnt_a.value(0)
        cnt_b.value(0)
        return a, b

    print("Using hardware counters with glitch filter")

except Exception as e:
    # Fallback: interrupts on both pins, no glitch filter
    print("Hardware counter not available (", repr(e), ") - using interrupts")
    count_a = 0
    count_b = 0

    def irq_a(pin):
        global count_a
        count_a += 1

    def irq_b(pin):
        global count_b
        count_b += 1

    enc_a.irq(trigger=Pin.IRQ_RISING, handler=irq_a)
    enc_b.irq(trigger=Pin.IRQ_RISING, handler=irq_b)

    def read_counts():
        global count_a, count_b
        state = machine.disable_irq()
        a, b = count_a, count_b
        count_a = 0
        count_b = 0
        machine.enable_irq(state)
        return a, b


# ---------------- Test ----------------
def run(direction, speed, seconds):
    """Ramp up, run, ramp down. Returns (total A, total B), or None if it stalled."""
    set_power(0)
    time.sleep(0.05)
    dir_pin.value(direction)
    read_counts()  # clear old counts
    total_a = 0
    total_b = 0

    print("DIR", direction, ": ramping up to", speed, "%")
    for s in range(0, speed + 1, 5):
        set_power(s)
        time.sleep(0.05)
    a, b = read_counts()
    total_a += a
    total_b += b

    zero_run = 0
    t_end = time.ticks_add(time.ticks_ms(), int(seconds * 1000))
    while time.ticks_diff(t_end, time.ticks_ms()) > 0:
        time.sleep(0.1)
        a, b = read_counts()
        total_a += a
        total_b += b
        print("  DIR", direction, "  A:", a, "  B:", b,
              "   total A:", total_a, "  total B:", total_b)
        if a == 0:
            zero_run += 1
            if STALL_CHECK and zero_run >= STALL_READS:
                set_power(0)
                if total_b > 0:
                    print("STOPPED: B is counting but A is not. Check the yellow",
                          "wire and its divider (row 27, GPIO 42).")
                else:
                    print("STOPPED: no pulses on A or B for", STALL_READS * 0.1,
                          "s. Motor stalled, or the encoder has no 5V / GND.")
                return None
        else:
            zero_run = 0

    for s in range(speed, -1, -5):
        set_power(s)
        time.sleep(0.05)
    a, b = read_counts()
    total_a += a
    total_b += b
    print("DIR", direction, "done. Total A:", total_a, "  Total B:", total_b)
    if total_b == 0:
        print("  WARNING: B never counted. Check the white wire and its",
              "divider (row 32, GPIO 38).")
    return total_a, total_b


try:
    print("Lift test starting in 2 s. Lift should be at mid-height.")
    time.sleep(2)

    r0 = run(0, SPEED, RUN_TIME)
    if r0 is not None:
        print("Watch the lift: did DIR 0 go UP or DOWN?")
        time.sleep(PAUSE)
        r1 = run(1, SPEED, RUN_TIME)
        if r1 is not None:
            print("Results -> DIR 0: A", r0[0], "B", r0[1],
                  "   DIR 1: A", r1[0], "B", r1[1])
            print("A and B should be close to each other in each direction.")
    print("Test finished.")

finally:
    set_power(0)
    dir_pin.value(0)
    print("Lift motor stopped")
