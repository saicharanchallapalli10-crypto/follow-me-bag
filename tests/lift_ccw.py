# Run ONLY the lift motor with DIR 1 (= lift DOWN) at 80% until the Stop button (GPIO 6) is pressed.
# Also stops on: Ctrl+C / STOP task, stall (encoder B no pulses for 0.3 s), bottom switch (GPIO 7),
# or MAX_S as a backstop. Wheels held off.
from machine import Pin, PWM
import time

SPEED = 80       # % power
DIRECTION = 1    # MD10C DIR: 1 = counter-clockwise, 0 = clockwise
MAX_S = 30       # backstop: never runs longer than this (s)

# all motor pins off first
lift = PWM(Pin(14), freq=1000, duty_u16=0)
dir_pin = Pin(13, Pin.OUT, value=0)
PWM(Pin(18), freq=1000, duty_u16=0)
PWM(Pin(10), freq=1000, duty_u16=0)
for p in (8, 9, 11, 12):
    Pin(p, Pin.OUT, value=0)

stop_btn = Pin(6, Pin.IN, Pin.PULL_UP)  # pressed = 0
bottom = Pin(7, Pin.IN, Pin.PULL_UP)    # pressed = 0
enc_b = Pin(38, Pin.IN, Pin.PULL_UP)
pulses = 0

def count(pin):
    global pulses
    pulses += 1

enc_b.irq(trigger=Pin.IRQ_RISING, handler=count)

def power(p):
    lift.duty_u16(int(p * 655))

try:
    if stop_btn.value() == 0:
        print("Stop button is pressed - not running. Release it first.")
    elif bottom.value() == 0:
        print("Bottom switch is pressed - not running.")
    else:
        dir_pin.value(DIRECTION)
        print("Lift running counter-clockwise at", SPEED, "% - press the Stop button (GPIO 6) to stop")
        start = time.ticks_ms()
        last_pulse = start
        last_count = 0
        last_print = start
        why = "max time %d s" % MAX_S
        while time.ticks_diff(time.ticks_ms(), start) < MAX_S * 1000:
            now = time.ticks_ms()
            t = time.ticks_diff(now, start)
            power(min(SPEED, SPEED * t / 500))          # ramp up over 0.5 s
            if pulses != last_count:
                last_count = pulses
                last_pulse = now
            if stop_btn.value() == 0:
                why = "Stop button"
                break
            if bottom.value() == 0:
                why = "bottom switch"
                break
            if t > 500 and time.ticks_diff(now, last_pulse) > 300:
                why = "STALL (no encoder B pulses for 0.3 s)"
                break
            if time.ticks_diff(now, last_print) >= 1000:
                last_print = now
                print("  running", t // 1000, "s   pulses:", pulses)
            time.sleep_ms(5)
        power(0)
        print("Stopped:", why, "  encoder B pulses:", pulses)
finally:
    power(0)
    dir_pin.value(0)
    print("finally ran: lift off")
