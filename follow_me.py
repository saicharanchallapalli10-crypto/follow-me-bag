from machine import Pin, PWM, UART
import machine
import select
import sys
import time

# Follow-me bag: UWB distance following (wheels) + scissor lift on terminal keys.
#
# Lift keys (type in the Run terminal or Thonny's shell, then press Enter):
#   u = lift up     d = lift down     s = stop the lift
# Each u / d press runs the lift for LIFT_RUN_MS (press the same key again to keep going).
# Ctrl+C (or the STOP task) stops everything.
#
# INTERLOCK: the wheels and the lift are never powered at the same time.
#   - A lift request first stops the wheels and waits until both wheel encoders read 0.
#   - While the lift runs, the wheels are held at 0. Following resumes after the lift stops.
#   - Every motor write checks the real PWM duty of the other motors. If the wheels and the
#     lift would ever be on together, ALL motors are cut and the program ends ("INTERLOCK").

# ======================= Settings =======================
STOP_DIST  = 100   # cm: at or closer than this, the bag stops
START_DIST = 115   # cm: must be farther than this to start again (stops stutter)
FULL_DIST  = 300   # cm: at or beyond this, full speed
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

# ---- Lift ----
LIFT_SPEED     = 40    # % lift power while moving. Keep it low until the lift is tested
LIFT_RAMP      = 10.0  # most the lift power can change per 0.1 s step (%)
LIFT_RUN_MS    = 1000  # how long one u / d press runs the lift (ms, including the ramp up)
LIFT_MAX_MS    = 4000  # longest continuous lift run, even if the key is pressed again (ms)
LIFT_UP_DIR    = 0     # MD10C DIR value that moves the lift UP (lift_buttons test 2026-11-20: DIR 0 = UP)
STALL_READS    = 3     # this many 0.1 s readings with 0 pulses on lift encoder A = stalled
STALL_CHECK    = True  # set False only if lift encoder A is not working
WHEEL_STOP_MS  = 1500  # wait at most this long for the wheels to stop turning before lifting
LIFT_SETTLE_MS = 300   # pause after the lift stops before the wheels may run again

# ======================= Wheel motors (DFR0601) =======================
pwm1 = PWM(Pin(18), freq=1000, duty_u16=0)
ina1 = Pin(8, Pin.OUT, value=0)
inb1 = Pin(9, Pin.OUT, value=0)
pwm2 = PWM(Pin(10), freq=1000, duty_u16=0)
ina2 = Pin(11, Pin.OUT, value=0)
inb2 = Pin(12, Pin.OUT, value=0)

# ======================= Lift motor (MD10C) =======================
# GPIO 14 -> MD10C PWM, GPIO 13 -> MD10C DIR, ESP32 G -> MD10C GND
pwm_lift = PWM(Pin(14), freq=1000, duty_u16=0)
dir_lift = Pin(13, Pin.OUT, value=0)

# ======================= Interlock =======================
def all_off():
    """Cut every motor, without any checks."""
    pwm_lift.duty_u16(0)
    pwm1.duty_u16(0)
    pwm2.duty_u16(0)
    ina1.value(0)
    inb1.value(0)
    ina2.value(0)
    inb2.value(0)

def wheels_powered():
    return pwm1.duty_u16() != 0 or pwm2.duty_u16() != 0

def lift_powered():
    return pwm_lift.duty_u16() != 0

def interlock_trip(why):
    all_off()
    print("INTERLOCK:", why, "- all motors off, program stopped")
    raise RuntimeError("INTERLOCK: " + why)

def set_motor(pwm, ina, inb, speed):
    speed = max(-100, min(100, speed))
    if speed != 0 and lift_powered():
        interlock_trip("wheel command while the lift is powered")
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

def set_lift(p):
    p = max(0, min(100, p))
    if p != 0 and wheels_powered():
        interlock_trip("lift command while the wheels are powered")
    pwm_lift.duty_u16(int(p * 655))

def set_lift_dir(d):
    if lift_powered():
        interlock_trip("lift direction change while the lift is powered")
    dir_lift.value(d)

# ======================= Wheel encoders =======================
# Motor 1's encoder is on GPIO 40, motor 2's on GPIO 39
enc1_pin = Pin(40, Pin.IN, Pin.PULL_UP)
enc2_pin = Pin(39, Pin.IN, Pin.PULL_UP)
# Lift encoder: A (yellow, through divider) on GPIO 42, B (white, through divider) on GPIO 38
lift_a_pin = Pin(42, Pin.IN, Pin.PULL_UP)
lift_b_pin = Pin(38, Pin.IN, Pin.PULL_UP)

try:
    from machine import Counter
    # Hardware counters 0 and 1 = wheels, 2 and 3 = lift
    cnt1 = Counter(0, enc1_pin, edge=Counter.RISING, filter_ns=FILTER_NS)
    cnt2 = Counter(1, enc2_pin, edge=Counter.RISING, filter_ns=FILTER_NS)
    cnt_la = Counter(2, lift_a_pin, edge=Counter.RISING, filter_ns=FILTER_NS)
    cnt_lb = Counter(3, lift_b_pin, edge=Counter.RISING, filter_ns=FILTER_NS)

    def read_counts():
        c1 = cnt1.value()
        c2 = cnt2.value()
        cnt1.value(0)
        cnt2.value(0)
        return c1, c2

    def read_lift_counts():
        a = cnt_la.value()
        b = cnt_lb.value()
        cnt_la.value(0)
        cnt_lb.value(0)
        return a, b

    print("Encoders: hardware counter with glitch filter")
except Exception as e:
    print("Hardware counter not available (", repr(e), ") - using interrupts")
    count1 = 0
    count2 = 0
    count_la = 0
    count_lb = 0

    def enc1(pin):
        global count1
        count1 += 1

    def enc2(pin):
        global count2
        count2 += 1

    def enc_la(pin):
        global count_la
        count_la += 1

    def enc_lb(pin):
        global count_lb
        count_lb += 1

    enc1_pin.irq(trigger=Pin.IRQ_RISING, handler=enc1)
    enc2_pin.irq(trigger=Pin.IRQ_RISING, handler=enc2)
    lift_a_pin.irq(trigger=Pin.IRQ_RISING, handler=enc_la)
    lift_b_pin.irq(trigger=Pin.IRQ_RISING, handler=enc_lb)

    def read_counts():
        global count1, count2
        state = machine.disable_irq()
        c1 = count1
        c2 = count2
        count1 = 0
        count2 = 0
        machine.enable_irq(state)
        return c1, c2

    def read_lift_counts():
        global count_la, count_lb
        state = machine.disable_irq()
        a = count_la
        b = count_lb
        count_la = 0
        count_lb = 0
        machine.enable_irq(state)
        return a, b

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

# ======================= Keys (terminal input) =======================
keys = select.poll()
keys.register(sys.stdin, select.POLLIN)

def read_keys():
    """Return the key letters typed since the last call (never waits)."""
    got = ""
    for _ in range(20):
        if not keys.poll(0):
            break
        c = sys.stdin.read(1)
        if c and c in "udsUDS":
            got += c.lower()
    return got

# ======================= Main loop =======================
DRIVE, STOP_WHEELS, LIFT, SETTLE = "DRIVE", "STOP_WHEELS", "LIFT", "SETTLE"
mode = DRIVE

recent = []         # last few UWB readings
dist = None         # smoothed distance (cm)
last_reading = time.ticks_ms()
moving = False
base = 0.0          # motor 2 power (%)
trim = 0.0          # extra power for motor 1 so it matches motor 2
step_n = 0
next_step = time.ticks_add(time.ticks_ms(), 100)

lift_dir = LIFT_UP_DIR  # requested lift direction (DIR pin value)
lift_power = 0.0        # current lift power (%)
lift_start = 0          # ms: when the lift started running
lift_end = 0            # ms: when the lift should start ramping down
mode_since = 0          # ms: when the current mode started
still_steps = 0         # steps in a row with both wheel encoders at 0
zero_run = 0            # steps in a row with 0 pulses on lift encoder A
lift_total_a = 0
lift_total_b = 0

def lift_name(d):
    return "UP" if d == LIFT_UP_DIR else "DOWN"

def stop_lift(why):
    global lift_power, mode, mode_since
    set_lift(0)
    lift_power = 0.0
    mode = SETTLE
    mode_since = time.ticks_ms()
    print("Lift stopped:", why, "  total A:", lift_total_a, "  total B:", lift_total_b)

print("Follow-me running. Press Stop (Ctrl+C) to quit.")
print("Lift keys: u + Enter = up, d + Enter = down, s + Enter = stop lift.")
all_off()
read_counts()
read_lift_counts()
try:
    while True:
        # keep reading UWB between control steps
        for d in read_distances():
            recent = (recent + [d])[-SMOOTH:]
            dist = median(recent)
            last_reading = time.ticks_ms()

        # ---- lift keys ----
        for k in read_keys():
            now = time.ticks_ms()
            want = LIFT_UP_DIR if k == "u" else 1 - LIFT_UP_DIR
            if k == "s":
                if mode == LIFT:
                    stop_lift("s pressed")
                elif mode == STOP_WHEELS:
                    mode = DRIVE
                    print("Lift request cancelled")
            elif mode == LIFT:
                if want == lift_dir:
                    # same key again: keep going, up to LIFT_MAX_MS in total
                    lift_end = min(time.ticks_add(now, LIFT_RUN_MS),
                                   time.ticks_add(lift_start, LIFT_MAX_MS))
                else:
                    stop_lift("opposite key pressed (press it again to reverse)")
            else:
                if mode == DRIVE:
                    print("Lift", lift_name(want), "requested: stopping the wheels first")
                elif want != lift_dir:
                    print("Lift request changed to", lift_name(want))
                lift_dir = want
                mode = STOP_WHEELS
                mode_since = now
                still_steps = 0

        if time.ticks_diff(time.ticks_ms(), next_step) < 0:
            time.sleep_ms(5)
            continue
        next_step = time.ticks_add(next_step, 100)
        step_n += 1
        now = time.ticks_ms()

        if mode == DRIVE or mode == STOP_WHEELS:
            # ---- decide the target speed ----
            lost = time.ticks_diff(now, last_reading) > LOST_MS
            if mode == STOP_WHEELS or lost or dist is None:
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

            if mode == STOP_WHEELS:
                # ---- wait until the wheels are unpowered AND have stopped turning ----
                if base == 0 and not wheels_powered():
                    still_steps = still_steps + 1 if (c1 == 0 and c2 == 0) else 0
                    waited = time.ticks_diff(now, mode_since)
                    if still_steps >= 2 or waited > WHEEL_STOP_MS:
                        if still_steps < 2:
                            print("Wheels still turning after", WHEEL_STOP_MS,
                                  "ms (unpowered) - starting the lift anyway")
                        set_lift_dir(lift_dir)
                        read_lift_counts()
                        lift_power = 0.0
                        lift_total_a = 0
                        lift_total_b = 0
                        zero_run = 0
                        lift_start = now
                        lift_end = time.ticks_add(now, LIFT_RUN_MS)
                        mode = LIFT
                        mode_since = now
                        print("Wheels off. Lift", lift_name(lift_dir), "running")
            elif step_n % 3 == 0:
                if lost:
                    print("NO TAG for", LOST_MS, "ms - stopped")
                else:
                    print("dist:", dist, "cm  target:", round(target), "%  base:", round(base, 1),
                          "%  M1:", c1, " M2:", c2, " M1 power:", round(m1, 1))

        elif mode == LIFT:
            # wheels stay off the whole time the lift runs
            motor1(0)
            motor2(0)
            read_counts()
            a, b = read_lift_counts()
            lift_total_a += a
            lift_total_b += b

            ramping_down = time.ticks_diff(now, lift_end) >= 0
            if ramping_down:
                lift_power = max(0.0, lift_power - LIFT_RAMP)
            else:
                lift_power = min(float(LIFT_SPEED), lift_power + LIFT_RAMP)
            set_lift(lift_power)

            # stall check only while running at full lift power
            if not ramping_down and lift_power >= LIFT_SPEED:
                zero_run = zero_run + 1 if a == 0 else 0
                if STALL_CHECK and zero_run >= STALL_READS:
                    if lift_total_b > 0:
                        stop_lift("STALL? B is counting but A is not - check the yellow wire "
                                  "and its divider (GPIO 42)")
                    else:
                        stop_lift("STALL: no pulses on A or B - lift stuck/at the end, "
                                  "or the encoder has no 5V / GND")
                    continue

            if step_n % 3 == 0:
                print("LIFT", lift_name(lift_dir), " power:", round(lift_power), "%  A:", a,
                      " B:", b, "  total A:", lift_total_a, " total B:", lift_total_b)

            if ramping_down and lift_power == 0:
                stop_lift("run time done")

        elif mode == SETTLE:
            # everything off; wait a moment before the wheels may run again
            set_lift(0)
            motor1(0)
            motor2(0)
            read_counts()
            read_lift_counts()
            if time.ticks_diff(now, mode_since) >= LIFT_SETTLE_MS:
                mode = DRIVE
                moving = False
                base = 0.0
                print("Following again")

finally:
    all_off()
    uart.deinit()
    print("Motors stopped (wheels and lift)")
