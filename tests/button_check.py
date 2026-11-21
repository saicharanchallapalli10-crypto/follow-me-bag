# Button / switch check: prints which button or switch is pressed. NO motors run.
#
# Prints the pin map and the start state, then a line every time something is pressed or released
# (30 ms debounce), plus an "all states" line every 3 s.
# Runs until you stop it: Ctrl+C, or python3 tools/esp32.py stop.
#
# Wiring (internal pull-ups, no resistors needed; released = 1, pressed = 0):
#   Up button     GPIO 4   one diagonal leg -> terminal 4, the opposite diagonal leg -> GND
#   Down button   GPIO 17  one diagonal leg -> terminal 17, the opposite diagonal leg -> GND
#   Stop button   GPIO 6   one diagonal leg -> terminal 6, the opposite diagonal leg -> GND
#   Bottom limit  GPIO 7   COM -> GND, NO -> terminal 7 (NC not connected)
# A part that is not wired yet just reads "released" (the pull-up holds it at 1).
from machine import Pin, PWM
import time

ONLY_GPIO = None     # check only this GPIO (4, 17, 6 or 7). None = check all four
LIMIT_PRESSED = 0    # bottom limit: 0 = NO wiring (pressed reads 0), 1 = NC wiring
BUTTON_PRESSED = 0
DEBOUNCE_MS = 30
REMIND_MS = 3000

# ---- ALL motor pins to 0 first (a floating GPIO 14 once started the lift) ----
lift_pwm = PWM(Pin(14), freq=1000, duty_u16=0)
lift_dir = Pin(13, Pin.OUT, value=0)
wheel_pwms = [PWM(Pin(18), freq=1000, duty_u16=0), PWM(Pin(10), freq=1000, duty_u16=0)]
wheel_dirs = [Pin(p, Pin.OUT, value=0) for p in (8, 9, 11, 12)]


def all_off():
    lift_pwm.duty_u16(0)
    lift_dir.value(0)
    for p in wheel_pwms:
        p.duty_u16(0)
    for p in wheel_dirs:
        p.value(0)


# (name, GPIO, pin value when pressed)
PARTS = [
    ("Up button", 4, BUTTON_PRESSED),
    ("Down button", 17, BUTTON_PRESSED),
    ("Stop button", 6, BUTTON_PRESSED),
    ("Bottom limit", 7, LIMIT_PRESSED),
]
if ONLY_GPIO is not None:
    PARTS = [p for p in PARTS if p[1] == ONLY_GPIO]


class Input:
    def __init__(self, name, gpio, pressed_value):
        self.name = name
        self.gpio = gpio
        self.pv = pressed_value
        self.pin = Pin(gpio, Pin.IN, Pin.PULL_UP)
        self.state = self.pin.value()   # debounced
        self.cand = self.state
        self.since = time.ticks_ms()
        self.presses = 0

    def word(self, v=None):
        return "PRESSED" if (self.state if v is None else v) == self.pv else "released"

    def update(self, now):
        raw = self.pin.value()
        if raw != self.cand:
            self.cand = raw
            self.since = now
        elif raw != self.state and time.ticks_diff(now, self.since) >= DEBOUNCE_MS:
            self.state = raw
            if self.word() == "PRESSED":
                self.presses += 1
            print("%-12s GPIO %d  %-8s (raw %d, presses %d)"
                  % (self.name, self.gpio, self.word(), raw, self.presses))


try:
    all_off()
    inputs = [Input(n, g, pv) for n, g, pv in PARTS]
    print("Button check - no motors. Pin map (released = 1, pressed = 0):")
    for i in inputs:
        print("  %-12s GPIO %d   now: %-8s (raw %d)" % (i.name, i.gpio, i.word(), i.state))
    print("Press each button / the switch one at a time.")
    last_remind = time.ticks_ms()
    while True:
        now = time.ticks_ms()
        for i in inputs:
            i.update(now)
        if time.ticks_diff(now, last_remind) >= REMIND_MS:
            last_remind = now
            print("  states: " + "   ".join("%s %s" % (i.name.split()[0], i.word()) for i in inputs))
        time.sleep_ms(2)
finally:
    all_off()
    print("finally ran: motors off")
