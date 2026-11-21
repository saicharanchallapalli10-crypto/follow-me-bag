# Pin finder: watches every free GPIO (internal pull-ups) for 30 s and prints any that goes LOW
# (pressed / touched to GND). Use it to find which pin a button is really on. No motors run.
from machine import Pin, PWM
import time

# all motor pins off (project rule)
PWM(Pin(14), freq=1000, duty_u16=0)
PWM(Pin(18), freq=1000, duty_u16=0)
PWM(Pin(10), freq=1000, duty_u16=0)
for p in (13, 8, 9, 11, 12):
    Pin(p, Pin.OUT, value=0)

# free pins only (not motors, encoders, UWB UART, USB, flash/PSRAM, LED)
FREE = (1, 2, 4, 5, 6, 7, 15, 16, 17, 41)
pins = {g: Pin(g, Pin.IN, Pin.PULL_UP) for g in FREE}
last = {g: p.value() for g, p in pins.items()}
print("Watching GPIO", FREE, "for 30 s. Press each button.")
print("Start: LOW (already pressed/grounded):", [g for g in FREE if last[g] == 0] or "none")

end = time.ticks_add(time.ticks_ms(), 30000)
while time.ticks_diff(end, time.ticks_ms()) > 0:
    for g, p in pins.items():
        v = p.value()
        if v != last[g]:
            print("GPIO", g, "PRESSED (low)" if v == 0 else "released")
            last[g] = v
    time.sleep_ms(30)
print("done")
