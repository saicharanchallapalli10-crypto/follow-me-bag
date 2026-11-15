from machine import UART, Pin
import time

# ---- 1. Is the sensor's TX line actually being driven? ----
# A working UART line sits HIGH (1) when idle. A floating or noisy wire jumps around.
rx = Pin(21, Pin.IN)
highs = 0
for i in range(2000):
    highs += rx.value()
    time.sleep_us(50)
print("GPIO 21 idle check: high", highs * 100 // 2000, "% of the time")
print("  (near 100% = sensor TX is driving the line;  jumping around = floating/noise)")
print()

# ---- 2. Try common baud rates and see which gives readable text ----
BAUDS = [115200, 9600, 19200, 38400, 57600, 230400, 460800, 921600, 1000000]

def readable(data):
    if not data:
        return 0
    ok = sum(1 for b in data if 32 <= b <= 126 or b in (9, 10, 13))
    return ok * 100 // len(data)

best = None
for baud in BAUDS:
    u = UART(1, baudrate=baud, tx=47, rx=21)
    time.sleep(0.1)
    while u.any():
        u.read()                      # throw away anything left over
    u.write("\r\nHELP\r\n")
    data = b""
    end = time.ticks_add(time.ticks_ms(), 1200)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if u.any():
            data += u.read()
        time.sleep(0.01)
    u.deinit()
    score = readable(data)
    found = b"INITF" in data or b"RESPF" in data
    print(baud, "baud:", len(data), "bytes,", score, "% readable", "<-- FOUND THE MENU" if found else "")
    if found and best is None:
        best = (baud, data)

print()
if best:
    print("Sensor answers at", best[0], "baud. Its reply:")
    print(best[1].decode("utf-8", "ignore"))
else:
    print("No baud rate gave the command list.")
