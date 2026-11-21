# Limit switch test on GPIO 7. Prints PRESSED / RELEASED every time the switch changes,
# plus a reminder line every 2 s with the current state.
#
# Wiring (no resistor needed, the internal pull-up is used):
#   switch COM -> GND
#   switch NO  -> GPIO 7     (NO = normally open: pin reads 0 when pressed)
# If you wire it to NC instead, set PRESSED_VALUE = 1 below.
#
# No motors move. All motor pins (wheels + lift) are held at 0 first, per the project rule.
# Runs until you stop it: Ctrl+C, or python3 tools/esp32.py stop.
from machine import Pin, PWM
import time

SWITCH_PIN = 7
PRESSED_VALUE = 0    # 0 for NO wiring, 1 for NC wiring
DEBOUNCE_MS = 20     # state must be stable this long before it counts
REMIND_MS = 2000

# Hold every motor off (an unconfigured GPIO 14 floats and can start the lift).
lift_pwm = PWM(Pin(14), freq=1000, duty_u16=0)
lift_dir = Pin(13, Pin.OUT, value=0)
wheels = [
    (PWM(Pin(18), freq=1000, duty_u16=0), Pin(8, Pin.OUT, value=0), Pin(9, Pin.OUT, value=0)),
    (PWM(Pin(10), freq=1000, duty_u16=0), Pin(11, Pin.OUT, value=0), Pin(12, Pin.OUT, value=0)),
]


def all_off():
    lift_pwm.duty_u16(0)
    lift_dir.value(0)
    for pwm, a, b in wheels:
        pwm.duty_u16(0)
        a.value(0)
        b.value(0)


sw = Pin(SWITCH_PIN, Pin.IN, Pin.PULL_UP)


def name(raw):
    return "PRESSED" if raw == PRESSED_VALUE else "RELEASED"


try:
    state = sw.value()
    presses = 0
    print("Limit switch on GPIO %d. Start state: %s (raw %d)" % (SWITCH_PIN, name(state), state))
    last_change = time.ticks_ms()
    last_remind = time.ticks_ms()
    candidate = state
    while True:
        now = time.ticks_ms()
        raw = sw.value()
        if raw != candidate:
            candidate = raw          # new reading, start the debounce timer
            last_change = now
        elif raw != state and time.ticks_diff(now, last_change) >= DEBOUNCE_MS:
            state = raw              # stable long enough: accept it
            if state == PRESSED_VALUE:
                presses += 1
            print("%s  (raw %d, presses so far %d)" % (name(state), state, presses))
        if time.ticks_diff(now, last_remind) >= REMIND_MS:
            print("  ...still %s" % name(state))
            last_remind = now
        time.sleep_ms(2)
finally:
    all_off()
    print("finally ran: motors off")
