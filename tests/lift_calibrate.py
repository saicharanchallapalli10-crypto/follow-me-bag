# Lift calibration: find LIFT_TOP_COUNTS for bag_main.py. Wheels held off the whole time.
#
#  1. Press Down: the lift goes down until the bottom switch (GPIO 7) -> HOMED, position 0.
#     (If it already rests on the switch at start, it is homed straight away.)
#  2. Press Up: it goes up and prints the position every 0.25 s. Press Stop (or Down) to stop.
#     Short Up presses (press Up, then Stop) let you creep up to the highest SAFE height.
#  3. Read the last "position" at that height and put it (minus a small margin) in
#     LIFT_TOP_COUNTS in bag_main.py AND bag_main_bench.py.
#
# There is NO soft top here (that is what you are finding), so watch the lift. It still stops on:
# Stop, the opposite button, a stall (encoder B no pulses for 0.3 s), the bottom switch (going down),
# and MAX_LIFT_S per move. Up is refused until the lift has been homed.
# Same position counting as bag_main.py (encoder B on GPIO 38, hardware counter, + up / - down).
# Ends with Ctrl+C or python3 tools/esp32.py stop (lift off).
from machine import Pin, PWM, Counter
import time

LIFT_SPEED = 80      # % (same as bag_main.py)
LIFT_RAMP_MS = 500
UP_DIR = 0           # DIR 0 = UP (same as bag_main.py)
MAX_LIFT_S = 8
STALL_MS = 300
STALL_GRACE_MS = 500
COAST_MS = 300
UP_PIN, DOWN_PIN, STOP_PIN, BOTTOM_PIN = 4, 17, 6, 7
LIMIT_PRESSED = 0    # same as bag_main.py

# ---- all motor pins off first ----
lift = PWM(Pin(14), freq=1000, duty_u16=0)
dir_pin = Pin(13, Pin.OUT, value=0)
PWM(Pin(18), freq=1000, duty_u16=0)
PWM(Pin(10), freq=1000, duty_u16=0)
for p in (8, 9, 11, 12):
    Pin(p, Pin.OUT, value=0)

cnt_b = Counter(3, Pin(38, Pin.IN, Pin.PULL_UP), edge=Counter.RISING, filter_ns=10000)
bottom = Pin(BOTTOM_PIN, Pin.IN, Pin.PULL_UP)

class Button:
    """Pressed = pin reads 0. press() is True once per press (30 ms debounce).
    A button held at the start is ignored until it is released."""
    def __init__(self, gpio):
        self.pin = Pin(gpio, Pin.IN, Pin.PULL_UP)
        self.state = self.pin.value()
        self.cand = self.state
        self.since = time.ticks_ms()
        self.ready = self.state == 1

    def press(self, now):
        raw = self.pin.value()
        if raw != self.cand:
            self.cand = raw
            self.since = now
            return False
        if raw == self.state or time.ticks_diff(now, self.since) < 30:
            return False
        self.state = raw
        if raw == 1:
            self.ready = True
            return False
        return self.ready

up = Button(UP_PIN)
down = Button(DOWN_PIN)
stop = Button(STOP_PIN)

def power(p):
    lift.duty_u16(int(p * 655))

def take():
    n = cnt_b.value()
    cnt_b.value(0)
    return n

moving = None        # None, "UP" or "DOWN"
last_move = None
start = 0
last_pulse = 0
coast_until = 0
pos = 0
homed = False
bottom_hits = 0
next_print = 0

def halt(why):
    global moving, coast_until
    power(0)
    coast_until = time.ticks_add(time.ticks_ms(), COAST_MS)
    print("STOP %s (%s)  position %d%s" % (moving, why, pos, "" if homed else "  (NOT HOMED)"))
    moving = None

def go(name, now):
    global moving, last_move, start, last_pulse
    if name == "DOWN" and bottom_hits >= 2:
        print("Down refused: bottom switch is pressed (homed, position 0)")
        return
    if name == "UP" and not homed:
        print("Up refused: NOT HOMED - press Down first to home on the bottom switch")
        return
    power(0)
    dir_pin.value(UP_DIR if name == "UP" else 1 - UP_DIR)
    take()
    start = now
    last_pulse = now
    moving = name
    last_move = name
    print("%s from position %d" % (name, pos))

print("Lift calibration. Up = GPIO %d, Down = GPIO %d, Stop = GPIO %d, bottom switch = GPIO %d."
      % (UP_PIN, DOWN_PIN, STOP_PIN, BOTTOM_PIN))
if bottom.value() == LIMIT_PRESSED:
    homed = True
    bottom_hits = 2
    print("HOMED at start (bottom switch pressed), position 0. Press Up to go up.")
else:
    print("NOT HOMED: press Down to home on the bottom switch.")
try:
    while True:
        now = time.ticks_ms()
        # position (same rule as bag_main.py)
        b = take()
        if b and (moving is not None or time.ticks_diff(now, coast_until) < 0):
            pos += b if last_move == "UP" else -b
            if moving is not None:
                last_pulse = now
        bottom_hits = bottom_hits + 1 if bottom.value() == LIMIT_PRESSED else 0
        if bottom_hits == 2:
            print("HOMED: bottom switch pressed, position %d -> 0" % pos)
        if bottom_hits >= 2:
            homed = True
            pos = 0

        u = up.press(now)
        d = down.press(now)
        s = stop.press(now)
        if moving is None:
            if u:
                go("UP", now)
            elif d:
                go("DOWN", now)
        else:
            t = time.ticks_diff(now, start)
            if s:
                halt("Stop button")
            elif (u and moving == "DOWN") or (d and moving == "UP"):
                halt("opposite button")
            elif moving == "DOWN" and bottom_hits >= 2:
                halt("bottom switch - homed")
            elif t >= MAX_LIFT_S * 1000:
                halt("max time %d s" % MAX_LIFT_S)
            elif t > STALL_GRACE_MS and time.ticks_diff(now, last_pulse) > STALL_MS:
                halt("STALL: no encoder B pulses for %d ms" % STALL_MS)
            else:
                power(min(LIFT_SPEED, LIFT_SPEED * t / LIFT_RAMP_MS))
                if time.ticks_diff(now, next_print) >= 0:
                    next_print = time.ticks_add(now, 250)
                    print("  %s  position %d" % (moving, pos))
        time.sleep_ms(5)
finally:
    power(0)
    dir_pin.value(0)
    print("finally ran: lift off.  Last position: %d%s" % (pos, "" if homed else " (NOT HOMED)"))
