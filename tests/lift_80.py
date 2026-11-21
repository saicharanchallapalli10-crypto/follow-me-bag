# Run ONLY the lift motor at 80%: ramp up 0.5 s, hold RUN_S, ramp down. Wheels held off.
# Stops early on a stall (lift encoder B no pulses for 0.3 s) or the bottom switch (GPIO 7).
from machine import Pin, PWM
import time

SPEED = 80       # % power
RUN_S = 1.0      # seconds at full power
DIRECTION = 1    # MD10C DIR: 0 = CW, 1 = CCW (which one is UP is not known yet)

# all motor pins off first
lift = PWM(Pin(14), freq=1000, duty_u16=0)
dir_pin = Pin(13, Pin.OUT, value=0)
PWM(Pin(18), freq=1000, duty_u16=0)
PWM(Pin(10), freq=1000, duty_u16=0)
for p in (8, 9, 11, 12):
    Pin(p, Pin.OUT, value=0)

enc_b = Pin(38, Pin.IN, Pin.PULL_UP)
bottom = Pin(7, Pin.IN, Pin.PULL_UP)   # pressed = 0
pulses = 0

def count(pin):
    global pulses
    pulses += 1

enc_b.irq(trigger=Pin.IRQ_RISING, handler=count)

def power(p):
    lift.duty_u16(int(p * 655))

try:
    if bottom.value() == 0:
        print("Bottom switch is pressed - not running. Move the lift off the switch first.")
    else:
        dir_pin.value(DIRECTION)
        print("Lift DIR", DIRECTION, "at", SPEED, "%")
        start = time.ticks_ms()
        stop_at = time.ticks_add(start, 500 + int(RUN_S * 1000))
        last_pulse = start
        last_count = 0
        why = "time done"
        while time.ticks_diff(stop_at, time.ticks_ms()) > 0:
            now = time.ticks_ms()
            t = time.ticks_diff(now, start)
            power(min(SPEED, SPEED * t / 500))          # ramp up over 0.5 s
            if pulses != last_count:
                last_count = pulses
                last_pulse = now
            if bottom.value() == 0:
                why = "bottom switch"
                break
            if t > 500 and time.ticks_diff(now, last_pulse) > 300:
                why = "STALL (no encoder B pulses for 0.3 s)"
                break
            time.sleep_ms(5)
        if why == "time done":
            for s in range(SPEED, -1, -10):              # ramp down
                power(s)
                time.sleep_ms(50)
        power(0)
        print("Stopped:", why, "  encoder B pulses:", pulses)
finally:
    power(0)
    dir_pin.value(0)
    print("finally ran: lift off")
