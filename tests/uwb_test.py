from machine import UART
import time

BAUD = 115200   # change this if the output looks like random symbols

# ESP32 TX on GPIO 47 -> sensor J10 pin 8, ESP32 RX on GPIO 21 <- sensor J10 pin 10
u = UART(1, baudrate=BAUD, tx=47, rx=21)

print("Listening for the UWB sensor at", BAUD, "baud. Press Stop to quit.")
last = time.ticks_ms()
try:
    while True:
        if u.any():
            line = u.readline()
            try:
                print(line.decode().strip())
            except Exception:
                print("RAW:", line)          # not readable text: wrong baud rate?
            last = time.ticks_ms()
        elif time.ticks_diff(time.ticks_ms(), last) > 2000:
            print("...nothing received in 2 s")
            last = time.ticks_ms()
        time.sleep(0.01)
finally:
    u.deinit()
    print("Stopped")
