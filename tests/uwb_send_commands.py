from machine import UART
import time

# ESP32 TX on GPIO 47 -> sensor J10 pin 8, ESP32 RX on GPIO 21 <- sensor J10 pin 10
u = UART(1, baudrate=115200, tx=47, rx=21)

def send(cmd, wait=1.5):
    print(">>", cmd)
    u.write(cmd + "\r\n")
    end = time.ticks_add(time.ticks_ms(), int(wait * 1000))
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if u.any():
            data = u.read()
            try:
                print(data.decode(), end="")
            except Exception:
                print("RAW:", data)
        time.sleep(0.01)
    print()

send("HELP")    # check that the board answers on the header pins
send("INITF")   # start ranging as the initiator
send("SAVE")    # keep UART 1 + INITF for every power-up
u.deinit()
print("Done")
