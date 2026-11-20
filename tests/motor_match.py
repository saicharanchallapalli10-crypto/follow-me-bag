from machine import Pin, PWM
import machine
import time

SPEED = 80     # base speed for both motors (0-100)
GAIN = 0.03    # how strongly motor 1 corrects to match motor 2
SPIKE_LIMIT = 0.4   # reject a reading more than 40% away from the recent median
HISTORY = 5         # how many recent good readings to compare against
MAX_BAD = 20        # this many rejected readings in a row (2 s) = real speed change
MAX_STEP = 2.0      # most M1 power can change in one 0.1 s step (%)
FILTER_NS = 10000   # ignore encoder pulses shorter than 10 microseconds

# Lift (MD10C) held OFF: a floating GPIO 14 can run the lift
PWM(Pin(14), freq=1000, duty_u16=0)
Pin(13, Pin.OUT, value=0)

pwm1 = PWM(Pin(18), freq=1000)
ina1 = Pin(8, Pin.OUT)
inb1 = Pin(9, Pin.OUT)
pwm2 = PWM(Pin(10), freq=1000)
ina2 = Pin(11, Pin.OUT)
inb2 = Pin(12, Pin.OUT)

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

# ---------------- Encoders ----------------
# Motor 1's encoder is on GPIO 40 and motor 2's on GPIO 39
# (the last run showed the GPIO 40 count following motor 1's power)
enc1_pin = Pin(40, Pin.IN, Pin.PULL_UP)
enc2_pin = Pin(39, Pin.IN, Pin.PULL_UP)

try:
    # Hardware pulse counter: counts in hardware and ignores glitches
    # shorter than FILTER_NS (the noise from the motor PWM)
    from machine import Counter
    cnt1 = Counter(0, enc1_pin, edge=Counter.RISING, filter_ns=FILTER_NS)
    cnt2 = Counter(1, enc2_pin, edge=Counter.RISING, filter_ns=FILTER_NS)

    def read_counts():
        c1 = cnt1.value()
        c2 = cnt2.value()
        cnt1.value(0)
        cnt2.value(0)
        return c1, c2

    print("Using hardware counter with glitch filter")

except Exception as e:
    # Fallback: interrupts with no glitch filter (same as before)
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

try:
    print("Ramping up to", SPEED, "%")
    for s in range(0, SPEED + 1, 5):
        motor1(s)
        motor2(s)
        time.sleep(0.05)

    m1_power = SPEED
    read_counts()   # clear counts from the ramp
    print("Matching speeds. Press Stop to stop.")

    hist1 = []      # last few good readings for each encoder
    hist2 = []
    bad_run = 0     # how many readings in a row were rejected

    def median(v):
        v = sorted(v)
        return v[len(v) // 2]

    def is_spike(c, hist):
        if len(hist) < HISTORY:
            return False                  # not enough data yet, accept it
        m = median(hist)
        return c > m * (1 + SPIKE_LIMIT) or c < m * (1 - SPIKE_LIMIT)

    while True:
        time.sleep(0.1)
        c1, c2 = read_counts()

        # if either encoder reads nothing, don't correct
        if c1 == 0 or c2 == 0:
            print("WARNING: encoder reading 0 -> M1:", c1, " M2:", c2,
                  " holding M1 power at", round(m1_power, 1))
            continue

        # spike check: a reading far from the recent median is noise
        if is_spike(c1, hist1) or is_spike(c2, hist2):
            bad_run += 1
            if bad_run < MAX_BAD:
                print("SPIKE ignored -> M1:", c1, " M2:", c2,
                      " holding M1 power at", round(m1_power, 1))
                continue
            # many in a row: the speed really changed, so start fresh
            print("Speed changed, resetting history")
            hist1 = []
            hist2 = []
        bad_run = 0

        hist1 = (hist1 + [c1])[-HISTORY:]
        hist2 = (hist2 + [c2])[-HISTORY:]

        # correction, limited so one reading can't swing power too far
        step = GAIN * (c2 - c1)
        step = max(-MAX_STEP, min(MAX_STEP, step))
        m1_power = max(0, min(100, m1_power + step))
        motor1(m1_power)
        print("M1:", c1, " M2:", c2, " M1 power:", round(m1_power, 1))

finally:
    motor1(0)
    motor2(0)
    print("Motors stopped")
