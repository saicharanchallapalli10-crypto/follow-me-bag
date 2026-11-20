# Board check for a new ESP32-S3 (nothing wired, USB only). No motors, ends by itself.
# Prints firmware, CPU, flash, RAM/PSRAM, MAC, checks machine.Counter, then the RGB LED test
# (GREEN driven from GPIO 48, then BLUE driven from GPIO 38), then the Wi-Fi radio.
# Whichever colour lights tells you which pin drives the LED on this board.
# (Lift encoder B is on GPIO 38, so if BLUE lights, the LED shares that pin.)
import sys
import os
import gc
import time
import machine
from machine import Pin

print("=== mcu_check ===")
print("firmware :", sys.implementation._machine, "- MicroPython",
      ".".join(str(v) for v in sys.implementation.version[:3]),
      "build", getattr(sys.implementation, "_build", "?"))
print("cpu MHz  :", machine.freq() // 1_000_000)
print("unique id:", machine.unique_id().hex())

try:
    import esp
    print("flash MB :", esp.flash_size() // (1024 * 1024))
except Exception as e:
    print("flash    : ?", e)

gc.collect()
free = gc.mem_free()
print("heap free: %d KB" % (free // 1024), "(PSRAM in use)" if free > 1_000_000 else "(NO PSRAM?)")

st = os.statvfs("/")
print("fs free  : %d KB of %d KB" % (st[0] * st[3] // 1024, st[0] * st[2] // 1024))
print("files    :", os.listdir("/"))

# Hardware pulse counter (used for the wheel and lift encoders). Input pin only, nothing driven.
try:
    c = machine.Counter(0, Pin(40, Pin.IN), filter_ns=1000)
    print("Counter  : OK, value", c.value())
    c.deinit()
except Exception as e:
    print("Counter  : FAILED", repr(e))

# RGB LED test.
try:
    import neopixel
except ImportError:
    neopixel = None
    print("LED      : neopixel module missing, skipped")

if neopixel:
    for pin_no, colour, rgb in ((48, "GREEN", (0, 40, 0)), (38, "BLUE", (0, 0, 40))):
        np = neopixel.NeoPixel(Pin(pin_no, Pin.OUT), 1)
        np[0] = rgb
        np.write()
        print("LED      : GPIO %d -> %s for 4 s. Watch the RGB LED." % (pin_no, colour))
        time.sleep(4)
        np[0] = (0, 0, 0)
        np.write()
        Pin(pin_no, Pin.IN)  # release the pin
        time.sleep(0.5)
    print("LED      : done. Which colour lit: GREEN (GPIO 48), BLUE (GPIO 38), both or none?")

# Wi-Fi radio (lift_web.py runs an access point). Scan only, then radio off. Last, because on
# 2026-11-20 switching Wi-Fi on reset the board (rst:0x1 POWERON = supply dip) when powered from
# the Mac's USB port. If the ROM boot log appears right after "wifi     : starting", that happened.
time.sleep_ms(100)
print("wifi     : starting (if the board reboots now, its power supply is too weak)")
time.sleep_ms(200)
try:
    import network
    w = network.WLAN(network.STA_IF)
    w.active(True)
    mac = w.config("mac")
    print("wifi MAC :", ":".join("%02x" % b for b in mac))
    nets = w.scan()
    print("wifi scan: OK,", len(nets), "networks seen")
    w.active(False)
except Exception as e:
    print("wifi     : FAILED", repr(e))

print("=== mcu_check done ===")
