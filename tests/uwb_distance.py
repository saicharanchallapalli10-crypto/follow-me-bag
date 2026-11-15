from machine import UART
import time

# ESP32 TX on GPIO 47 -> sensor J10 pin 8, ESP32 RX on GPIO 21 <- sensor J10 pin 10
u = UART(1, baudrate=115200, tx=47, rx=21)

SMOOTH = 5      # median of the last 5 good readings (removes one-off jumps)
TAG = "distance[cm]="

buf = ""
recent = []

def read_distances():
    """Return a list of new distances (cm) from complete SUCCESS readings."""
    global buf
    if u.any():
        try:
            buf += u.read().decode()
        except Exception:
            pass                        # skip a chunk that isn't clean text
    found = []
    while True:
        i = buf.find(TAG)
        if i < 0:
            break
        j = buf.find("]", i + len(TAG))   # skip the "]" inside "distance[cm]"
        if j < 0:
            break                       # reading not complete yet, wait for more
        start = buf.rfind("[", 0, i)
        ok = start >= 0 and "SUCCESS" in buf[start:i]
        try:
            d = int(buf[i + len(TAG):j])
        except ValueError:
            d = None
        buf = buf[j + 1:]
        if ok and d is not None:
            found.append(d)
    if len(buf) > 2000:
        buf = buf[-500:]                # never let leftovers pile up
    return found

def median(v):
    s = sorted(v)
    return s[len(s) // 2]

print("Reading UWB distance. Press Stop to quit.")
last_seen = time.ticks_ms()
try:
    while True:
        for d in read_distances():
            recent = (recent + [d])[-SMOOTH:]
            print("raw:", d, "cm   smoothed:", median(recent), "cm")
            last_seen = time.ticks_ms()
        if time.ticks_diff(time.ticks_ms(), last_seen) > 2000:
            print("no readings for 2 s - is the tag on and ranging?")
            last_seen = time.ticks_ms()
        time.sleep(0.01)
finally:
    u.deinit()
    print("Stopped")
