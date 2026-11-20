# Lift DIRECTION test: does the MD10C DIR pin (GPIO 13) really reverse the lift?
# Counts lift encoder A (GPIO 42) with B (GPIO 38) as the direction signal (quadrature), so the
# count goes UP in one direction and DOWN in the other. Rising-edge counts (lift_test_encoder.py)
# cannot show this.
#   DIR 0: ramp to 40%, ~1 s, ramp down. Pause 1.5 s. DIR 1: the same. About 7 s in total.
# Opposite signs for DIR 0 and DIR 1 = DIR works. Same sign = check the DIR wire (GPIO 13 -> MD10C DIR).
# Lift at MID-HEIGHT. Wheels held off. Lift goes to 0 on any exit (finally).
from machine import Pin, PWM
import time
import esp32

SPEED = 40          # lift power (%)
RUN_TIME = 1.0      # seconds at full test power per direction
PAUSE = 1.5         # seconds between directions
# FIND-UP mode: set WATCH_DIR to 0 or 1 to run only that direction, slower and longer, so you can see
# which way it goes; then (pause) it drives back the same amount in the other direction. None = normal test.
WATCH_DIR = 0
WATCH_SPEED = 30
WATCH_TIME = 2.5
if WATCH_DIR is not None:
    SPEED, RUN_TIME, PAUSE = WATCH_SPEED, WATCH_TIME, 3.0
STALL_READS = 3     # 0.1 s readings in a row with no movement at full power = stop

# Wheels held OFF first (both DFR0601 channels).
for _p in (18, 10):
    PWM(Pin(_p), freq=1000, duty_u16=0)
for _p in (8, 9, 11, 12):
    Pin(_p, Pin.OUT, value=0)

# Lift (MD10C), off.
pwm = PWM(Pin(14), freq=1000, duty_u16=0)
dir_pin = Pin(13, Pin.OUT, value=0)

# Quadrature count: rising edges of A count +1 while B is high, -1 while B is low.
enc_a = Pin(42, Pin.IN, Pin.PULL_UP)
enc_b = Pin(38, Pin.IN, Pin.PULL_UP)
pcnt = esp32.PCNT(2, pin=enc_a, rising=esp32.PCNT.INCREMENT, mode_pin=enc_b,
                  mode_low=esp32.PCNT.REVERSE, filter=1000)
pcnt.start()


def take():
    v = pcnt.value()
    pcnt.value(0)
    return v


def set_power(p):
    pwm.duty_u16(int(max(0, min(100, p)) * 655))


def run(direction):
    """Ramp up, hold, ramp down in one direction. Returns the signed count, or None if stalled."""
    set_power(0)
    time.sleep(0.05)
    dir_pin.value(direction)
    take()
    total = 0
    print("DIR", direction, ": ramping up to", SPEED, "%")
    for s in range(0, SPEED + 1, 5):
        set_power(s)
        time.sleep(0.05)
    total += take()
    still = 0
    t_end = time.ticks_add(time.ticks_ms(), int(RUN_TIME * 1000))
    while time.ticks_diff(t_end, time.ticks_ms()) > 0:
        time.sleep(0.1)
        n = take()
        total += n
        print("  DIR", direction, "  signed count:", n, "   total:", total)
        still = still + 1 if n == 0 else 0
        if still >= STALL_READS:
            set_power(0)
            print("STOPPED: no encoder movement for", STALL_READS * 0.1, "s (stuck, at an end, or encoder problem)")
            return None
    for s in range(SPEED, -1, -5):
        set_power(s)
        time.sleep(0.05)
    time.sleep(0.2)          # let it coast to a stop, keep counting
    total += take()
    print("DIR", direction, "done. Signed total:", total)
    return total


try:
    print("Lift direction test starting in 2 s. Lift should be at mid-height.")
    time.sleep(2)
    if WATCH_DIR is not None:
        print(">>> WATCH NOW: DIR", WATCH_DIR, "for", WATCH_TIME, "s at", WATCH_SPEED, "%. Is it going UP or DOWN?")
        rw = run(WATCH_DIR)
        if rw is not None:
            print("Pause", PAUSE, "s, then driving back (DIR", 1 - WATCH_DIR, ") to about the start height")
            time.sleep(PAUSE)
            rb = run(1 - WATCH_DIR)
            print("RESULT  watched DIR", WATCH_DIR, ":", rw, "   return DIR", 1 - WATCH_DIR, ":", rb)
    else:
        r0 = run(0)
        r1 = None
        if r0 is not None:
            time.sleep(PAUSE)
            r1 = run(1)
        print("RESULT  DIR 0:", r0, "   DIR 1:", r1)
        if r0 is not None and r1 is not None:
            if r0 * r1 < 0:
                print("DIR WORKS: the two directions have opposite signs.")
                print("Positive count = DIR", 0 if r0 > 0 else 1, "  Negative count = DIR", 0 if r0 < 0 else 1)
            elif r0 == 0 or r1 == 0:
                print("One direction did not move. Check the encoder and the lift.")
            else:
                print("SAME SIGN both times: the lift went the same way twice. Check the DIR wire (GPIO 13 -> MD10C DIR).")
finally:
    set_power(0)
    dir_pin.value(0)
    try:
        pcnt.deinit()
    except Exception:
        pass
    print("Lift motor stopped")
