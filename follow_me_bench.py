from machine import Pin, PWM, UART
import machine
import time

# ======================= Settings =======================
STOP_DIST  = 30    # cm: at or closer than this, the bag stops   (BENCH TEST - real: 100)
START_DIST = 40    # cm: must be farther than this to start again (BENCH TEST - real: 115)
FULL_DIST  = 100   # cm: at or beyond this, full speed            (BENCH TEST - real: 300)
MIN_SPEED  = 35    # % power when it starts moving (enough to overcome friction)
MAX_SPEED  = 80    # % power at FULL_DIST and beyond
RAMP_UP    = 3.0   # most the base speed can rise per 0.1 s step (%)
RAMP_DOWN  = 10.0  # most the base speed can drop per 0.1 s step (%)
LOST_MS    = 1000  # stop if no UWB reading for this long (ms)

GAIN      = 0.03   # motor 1 correction per count of difference
MAX_STEP  = 2.0    # most the correction can change per step (%)
MAX_TRIM  = 20.0   # most motor 1 may differ from motor 2 (%)
FILTER_NS = 10000  # encoder glitch filter: ignore pulses shorter than 10 us
SMOOTH    = 5      # median of the last 5 UWB readings

# ======================= Motors =======================
pwm1 = PWM(Pin(18), freq=1000, duty_u16=0)
ina1 = Pin(8, Pin.OUT, value=0)
inb1 = Pin(9, Pin.OUT, value=0)
pwm2 = PWM(Pin(10), freq=1000, duty_u16=0)
ina2 = Pin(11, Pin.OUT, value=0)
inb2 = Pin(12, Pin.OUT, value=0)

def set_motor(pwm, ina, inb, speed):
    speed = max(-100, min(100, speed))
    if speed > 0:
        ina.value(1)
        inb.value(0)
    elif speed < 0:
        ina.value(0)
        inb.value(1)
    else:
        ina.value(0)
        inb.value(0)
    pwm.duty_u16(int(abs(speed) * 655))

def motor1(speed):
    set_motor(pwm1, ina1, inb1, speed)

def motor2(speed):
    set_motor(pwm2, ina2, inb2, speed)

# ======================= Encoders =======================
# Motor 1's encoder is on GPIO 40, motor 2's on GPIO 39
enc1_pin = Pin(40, Pin.IN, Pin.PULL_UP)
enc2_pin = Pin(39, Pin.IN, Pin.PULL_UP)

try:
    from machine import Counter
    cnt1 = Counter(0, enc1_pin, edge=Counter.RISING, filter_ns=FILTER_NS)
    cnt2 = Counter(1, enc2_pin, edge=Counter.RISING, filter_ns=FILTER_NS)

    def read_counts():
        c1 = cnt1.value()
        c2 = cnt2.value()
        cnt1.value(0)
        cnt2.value(0)
        return c1, c2

    print("Encoders: hardware counter with glitch filter")
except Exception as e:
    print("Hardware counter not available (", repr(e), ") - using interrupts")
    count1 = 0
    count2 = 0

    def enc1(pin):
        global count1
        count1 += 1

    def enc2(pin):
        global count2
        count2 += 1

    enc1_pin.irq(trigger=Pin.IRQ_RISING, handler=enc1)
    enc2_pin.irq(trigger=Pin.IRQ_RISING, handler=enc2)

    def read_counts():
        global count1, count2
        state = machine.disable_irq()
        c1 = count1
        c2 = count2
        count1 = 0
        count2 = 0
        machine.enable_irq(state)
        return c1, c2

# ======================= UWB =======================
# ESP32 TX on GPIO 47 -> sensor J10 pin 8, ESP32 RX on GPIO 21 <- sensor J10 pin 10
uart = UART(1, baudrate=115200, tx=47, rx=21)
TAG = "distance[cm]="
buf = ""

def read_distances():
    """Return new distances (cm) from complete SUCCESS readings."""
    global buf
    if uart.any():
        try:
            buf += uart.read().decode()
        except Exception:
            pass
    found = []
    while True:
        i = buf.find(TAG)
        if i < 0:
            break
        j = buf.find("]", i + len(TAG))   # skip the "]" inside "distance[cm]"
        if j < 0:
            break                       # reading not complete yet
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
        buf = buf[-500:]
    return found

def median(v):
    s = sorted(v)
    return s[len(s) // 2]

def target_speed(d):
    """Linear from MIN_SPEED at STOP_DIST to MAX_SPEED at FULL_DIST."""
    if d >= FULL_DIST:
        return MAX_SPEED
    frac = (d - STOP_DIST) / (FULL_DIST - STOP_DIST)
    return MIN_SPEED + (MAX_SPEED - MIN_SPEED) * frac

# ======================= Main loop =======================
recent = []         # last few UWB readings
dist = None         # smoothed distance (cm)
last_reading = time.ticks_ms()
moving = False
base = 0.0          # motor 2 power (%)
trim = 0.0          # extra power for motor 1 so it matches motor 2
step_n = 0
next_step = time.ticks_add(time.ticks_ms(), 100)

print("Follow-me running. Press Stop to quit.")
read_counts()
try:
    while True:
        # keep reading UWB between control steps
        for d in read_distances():
            recent = (recent + [d])[-SMOOTH:]
            dist = median(recent)
            last_reading = time.ticks_ms()

        if time.ticks_diff(time.ticks_ms(), next_step) < 0:
            time.sleep_ms(5)
            continue
        next_step = time.ticks_add(next_step, 100)
        step_n += 1

        # ---- decide the target speed ----
        lost = time.ticks_diff(time.ticks_ms(), last_reading) > LOST_MS
        if lost or dist is None:
            moving = False
        elif moving and dist <= STOP_DIST:
            moving = False
        elif not moving and dist > START_DIST:
            moving = True
        target = target_speed(dist) if moving else 0.0

        # ---- ramp the base speed toward the target ----
        if target > base:
            base = min(target, base + RAMP_UP)
            if base < MIN_SPEED:
                base = MIN_SPEED            # start straight at a speed that moves
        else:
            base = max(target, base - RAMP_DOWN)
            if target == 0 and base < MIN_SPEED:
                base = 0.0                  # below this the wheels barely turn

        # ---- match motor 1 to motor 2 with the encoders ----
        c1, c2 = read_counts()
        if base > 0 and c1 > 0 and c2 > 0:
            step = max(-MAX_STEP, min(MAX_STEP, GAIN * (c2 - c1)))
            trim = max(-MAX_TRIM, min(MAX_TRIM, trim + step))

        m1 = max(0, min(100, base + trim)) if base > 0 else 0
        motor1(m1)
        motor2(base)

        if step_n % 3 == 0:
            if lost:
                print("NO TAG for", LOST_MS, "ms - stopped")
            else:
                print("dist:", dist, "cm  target:", round(target), "%  base:", round(base, 1),
                      "%  M1:", c1, " M2:", c2, " M1 power:", round(m1, 1))

finally:
    motor1(0)
    motor2(0)
    uart.deinit()
    print("Motors stopped")
