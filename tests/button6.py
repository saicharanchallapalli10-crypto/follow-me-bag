# Simple check of the button on GPIO 6. Runs for 20 s, then ends by itself.
from machine import Pin, PWM
import time

# all motor pins off (project rule)
PWM(Pin(14), freq=1000, duty_u16=0)
PWM(Pin(18), freq=1000, duty_u16=0)
PWM(Pin(10), freq=1000, duty_u16=0)
for p in (13, 8, 9, 11, 12):
    Pin(p, Pin.OUT, value=0)

button = Pin(6, Pin.IN, Pin.PULL_UP)
last = button.value()
print("GPIO 6 start:", "PRESSED" if last == 0 else "released")

end = time.ticks_add(time.ticks_ms(), 20000)
while time.ticks_diff(end, time.ticks_ms()) > 0:
    v = button.value()
    if v != last:
        print("GPIO 6:", "PRESSED" if v == 0 else "released")
        last = v
    time.sleep_ms(30)
print("done")
