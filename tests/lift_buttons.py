# Lift on the buttons only. The lift does nothing until you press a button. Wheels held off.
#   Up (GPIO 4)   = lift goes up and keeps going
#   Down (GPIO 17) = lift goes down and keeps going
#   Stop (GPIO 6) = stop
# While moving, the opposite button only stops it (press again to go the other way).
# It also stops by itself on: stall (encoder B no pulses for 0.3 s, after the first 0.5 s),
# the bottom switch (GPIO 7) when going down, or MAX_S.
# Ends with Ctrl+C or python3 tools/esp32.py stop (lift off).
from machine import Pin, PWM
import time

SPEED = 80       # % lift power
MAX_S = 8        # longest single move (s)
UP_DIR = 0       # DIR 0 = UP (lift_buttons test 2026-11-20)
DOWN_DIR = 1

# ---- all motor pins off first ----
lift = PWM(Pin(14), freq=1000, duty_u16=0)
dir_pin = Pin(13, Pin.OUT, value=0)
PWM(Pin(18), freq=1000, duty_u16=0)
PWM(Pin(10), freq=1000, duty_u16=0)
for p in (8, 9, 11, 12):
    Pin(p, Pin.OUT, value=0)

bottom = Pin(7, Pin.IN, Pin.PULL_UP)   # pressed = 0
enc_b = Pin(38, Pin.IN, Pin.PULL_UP)
pulses = 0

def count(pin):
    global pulses
    pulses += 1

enc_b.irq(trigger=Pin.IRQ_RISING, handler=count)

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

up = Button(4)
down = Button(17)
stop = Button(6)

def power(p):
    lift.duty_u16(int(p * 655))

moving = None    # None, "UP" or "DOWN"
start = 0
last_pulse = 0
last_count = 0

def halt(why):
    global moving
    power(0)
    print("STOP:", why, "  pulses this move:", pulses)
    moving = None

def go(name, d):
    global moving, start, last_pulse, last_count, pulses
    if name == "DOWN" and bottom.value() == 0:
        print("Down refused: bottom switch is pressed")
        return
    power(0)
    dir_pin.value(d)
    pulses = 0
    last_count = 0
    start = time.ticks_ms()
    last_pulse = start
    moving = name
    print(name)

print("Lift buttons ready: Up = GPIO 4, Down = GPIO 17, Stop = GPIO 6. Lift is OFF.")
try:
    while True:
        now = time.ticks_ms()
        u = up.press(now)
        d = down.press(now)
        s = stop.press(now)

        if moving is None:
            if u:
                go("UP", UP_DIR)
            elif d:
                go("DOWN", DOWN_DIR)
        else:
            t = time.ticks_diff(now, start)
            if pulses != last_count:
                last_count = pulses
                last_pulse = now
            if s:
                halt("Stop button")
            elif (u and moving == "DOWN") or (d and moving == "UP"):
                halt("opposite button")
            elif moving == "DOWN" and bottom.value() == 0:
                halt("bottom switch")
            elif t > 500 and time.ticks_diff(now, last_pulse) > 300:
                halt("STALL (no encoder B pulses for 0.3 s)")
            elif t >= MAX_S * 1000:
                halt("max time %d s" % MAX_S)
            else:
                power(min(SPEED, SPEED * t / 500))    # ramp up over 0.5 s
        time.sleep_ms(5)
finally:
    power(0)
    dir_pin.value(0)
    print("finally ran: lift off")
