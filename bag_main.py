BENCH = False   # True = bench distances (wheels in the air). bag_main_bench.py = this file with True.

# bag_main.py - the full bag program: UWB follow-me (wheels) + lift buttons with homing. No website.
#
# Run:  python3 tools/esp32.py run bag_main.py        (VS Code: open the file, Cmd+Shift+B)
# Stop: Ctrl+C in that terminal, or python3 tools/esp32.py stop. The finally block turns all motors off.
#
# FOLLOW-ME (same logic as follow_me.py)
#   Median of the last 5 UWB distances. Stops at <= STOP_DIST, starts again only beyond START_DIST.
#   Speed rises linearly from MIN_SPEED at STOP_DIST to MAX_SPEED at FULL_DIST.
#   Ramp +3% / -10% per 0.1 s. Stops if there is no UWB reading for 1 s.
#   Wheel 2 = base power, wheel 1 = base + trim from the encoder count difference.
# ARMING
#   After power-up the wheels do not move until the tag has been within STOP_DIST for 1 s
#   (stand next to the bag first). Prints "ARMED". No tag for 3 s -> "DISARMED", arm again the same way.
# LIFT BUTTONS (each pulls its pin to GND when pressed, internal pull-ups)
#   Up / Down start the lift that way; it keeps going until something stops it:
#     DOWN stops on: bottom switch (= homed, position 0), Stop, Up (stop only), stall, MAX_LIFT_S.
#     UP   stops on: position reaches LIFT_TOP_COUNTS (soft top), Stop, Down (stop only), stall, MAX_LIFT_S.
#   Position: lift encoder B pulses, + going up, - going down. Bottom switch pressed = homed, position 0.
#   NOT HOMED (after power-up, until the bottom switch is reached once): each Up move is limited to
#   UNHOMED_UP_S. Press Down to home.
#   Refuses: Down with the bottom switch pressed, Up at the soft top, anything while the Stop button is held.
#   Buttons held at power-up are ignored until they are released.
# WHEELS AND LIFT (LIFT_WHILE_DRIVING = False)
#   The lift only starts while the wheels are stopped. If the wheels start moving, the lift stops.
#   Every motor write checks the other motors' real PWM duty; on a conflict ALL motors are cut and
#   the program ends ("INTERLOCK").
# Find LIFT_TOP_COUNTS with tests/lift_calibrate.py.

# ======================= Settings =======================
if BENCH:
    STOP_DIST  = 30    # cm: at or closer than this, the bag stops
    START_DIST = 40    # cm: must be farther than this to start again (stops stutter)
    FULL_DIST  = 100   # cm: at or beyond this, full speed
    MAX_SPEED  = 80    # % power at FULL_DIST and beyond (never above 80)
else:
    STOP_DIST  = 100
    START_DIST = 115
    FULL_DIST  = 300
    MAX_SPEED  = 50    # first ground tests; raise later (never above 80)
MIN_SPEED  = 35    # % power when it starts moving (enough to overcome friction)
RAMP_UP    = 3.0   # most the base speed can rise per 0.1 s step (%)
RAMP_DOWN  = 10.0  # most the base speed can drop per 0.1 s step (%)
LOST_MS    = 1000  # stop if no UWB reading for this long (ms)
ARM_MS     = 1000  # tag must stay within STOP_DIST this long before the wheels may move (ms)
DISARM_MS  = 3000  # no UWB reading for this long -> disarmed (ms)

GAIN      = 0.03   # wheel 1 correction per count of difference
MAX_STEP  = 2.0    # most the correction can change per step (%)
MAX_TRIM  = 20.0   # most wheel 1 may differ from wheel 2 (%)
FILTER_NS = 10000  # encoder glitch filter: ignore pulses shorter than 10 us
SMOOTH    = 5      # median of the last 5 UWB readings

# ---- Lift ----
LIFT_SPEED         = 80     # % lift power while moving (tests/lift_buttons.py ran at 80)
LIFT_RAMP_MS       = 500    # lift power ramps from 0 to LIFT_SPEED over this time (ms). Stopping is immediate
UP_DIR             = 0      # MD10C DIR value that moves the lift UP (lift_buttons test 2026-11-20: DIR 0 = UP)
LIFT_TOP_COUNTS    = 3000   # soft top limit (encoder B pulses above the bottom switch). PLACEHOLDER: calibrate
MAX_LIFT_S         = 8      # longest single lift move (s)
UNHOMED_UP_S       = 1.5    # longest Up move before the lift has been homed (s)
STALL_CHECK        = True   # stop if encoder B gets no pulses (False only if encoder B is not working)
STALL_MS           = 300    # no encoder B pulse for this long while powered = stalled (ms)
STALL_GRACE_MS     = 500    # no stall check during the first 0.5 s of a move (ms)
COAST_MS           = 300    # pulses this long after a stop still count in that move's direction (ms)
LIFT_WHILE_DRIVING = False  # False: the lift only moves while the wheels are stopped

# ---- Buttons and the bottom limit switch (internal pull-ups) ----
UP_PIN         = 4
DOWN_PIN       = 17
STOP_PIN       = 6
BOTTOM_PIN     = 7     # bottom limit switch: COM -> GND, NO -> GPIO 7. There is no top switch
BUTTON_PRESSED = 0     # pin value when a button is pressed (pulls to GND = 0)
LIMIT_PRESSED  = 0     # pin value when the bottom switch is pressed: 0 = NO wiring, 1 = NC wiring
DEBOUNCE_MS    = 30    # a button must read the same for this long before it counts

# ---- Lift encoder ----
LIFT_B_PIN = 38    # white, through 10k/20k divider: position and stall check
LIFT_A_PIN = 42    # yellow, through 10k/20k divider: only printed. None = not used

STATUS_MS = 300    # status line every 0.3 s
LOOP_REPORT_MS = 5000   # worst loop time printed every 5 s

from machine import Pin, PWM, UART, Counter
import time

# ======================= ALL motor pins to 0 first =======================
# Wheels (DFR0601): channel 1 P/A/B = 18/8/9, channel 2 P/A/B = 10/11/12
pwm1 = PWM(Pin(18), freq=1000, duty_u16=0)
ina1 = Pin(8, Pin.OUT, value=0)
inb1 = Pin(9, Pin.OUT, value=0)
pwm2 = PWM(Pin(10), freq=1000, duty_u16=0)
ina2 = Pin(11, Pin.OUT, value=0)
inb2 = Pin(12, Pin.OUT, value=0)
# Lift (MD10C): GPIO 14 -> PWM, GPIO 13 -> DIR
pwm_lift = PWM(Pin(14), freq=1000, duty_u16=0)
dir_lift = Pin(13, Pin.OUT, value=0)

# ======================= Interlock =======================
def all_off():
    """Cut every motor, without any checks."""
    pwm_lift.duty_u16(0)
    dir_lift.value(0)
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
    if speed != 0 and lift_powered() and not LIFT_WHILE_DRIVING:
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
    if p != 0 and wheels_powered() and not LIFT_WHILE_DRIVING:
        interlock_trip("lift command while the wheels are powered")
    pwm_lift.duty_u16(int(p * 655))

def set_lift_dir(d):
    if lift_powered():
        interlock_trip("lift direction change while the lift is powered")
    dir_lift.value(d)

# ======================= Encoders (hardware counters) =======================
# Wheel 1 (channel 1) encoder on GPIO 40, wheel 2 (channel 2) on GPIO 39 (pairing check 2026-11-20)
cnt1 = Counter(0, Pin(40, Pin.IN, Pin.PULL_UP), edge=Counter.RISING, filter_ns=FILTER_NS)
cnt2 = Counter(1, Pin(39, Pin.IN, Pin.PULL_UP), edge=Counter.RISING, filter_ns=FILTER_NS)
cnt_lb = Counter(3, Pin(LIFT_B_PIN, Pin.IN, Pin.PULL_UP), edge=Counter.RISING, filter_ns=FILTER_NS)
cnt_la = None
if LIFT_A_PIN is not None:
    cnt_la = Counter(2, Pin(LIFT_A_PIN, Pin.IN, Pin.PULL_UP), edge=Counter.RISING, filter_ns=FILTER_NS)

def take(c):
    """Pulses since the last call (0 if the counter is not used)."""
    if c is None:
        return 0
    n = c.value()
    c.value(0)
    return n

def read_counts():
    return take(cnt1), take(cnt2)

# ======================= Buttons and the bottom switch =======================
class Button:
    """Debounced push button. update() returns True once per new press."""
    def __init__(self, gpio, name):
        self.gpio = gpio
        self.pin = Pin(gpio, Pin.IN, Pin.PULL_UP)
        self.name = name
        raw = self.pin.value()
        self.state = raw              # debounced value
        self.cand = raw               # latest raw value
        self.since = time.ticks_ms()  # when the raw value last changed
        self.ready = raw != BUTTON_PRESSED
        if not self.ready:
            print(name, "button held at power-up: ignored until it is released")

    def held(self):
        return self.state == BUTTON_PRESSED

    def update(self, now):
        raw = self.pin.value()
        if raw != self.cand:
            self.cand = raw
            self.since = now
            return False
        if raw == self.state or time.ticks_diff(now, self.since) < DEBOUNCE_MS:
            return False
        self.state = raw
        if raw != BUTTON_PRESSED:
            if not self.ready:
                print(self.name, "button released: active now")
            self.ready = True
            return False
        return self.ready

class Limit:
    """Limit switch: pressed after 2 pressed reads in a row (~5-10 ms, no 30 ms wait)."""
    def __init__(self, gpio):
        self.pin = Pin(gpio, Pin.IN, Pin.PULL_UP)
        self.hits = 0
        self.pressed = False

    def update(self):
        self.hits = self.hits + 1 if self.pin.value() == LIMIT_PRESSED else 0
        self.pressed = self.hits >= 2

btn_up = Button(UP_PIN, "Up")
btn_down = Button(DOWN_PIN, "Down")
btn_stop = Button(STOP_PIN, "Stop")
bottom = Limit(BOTTOM_PIN)

UP = UP_DIR
DOWN = 1 - UP_DIR

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

# ======================= Pin map (printed at every start) =======================
def word(v, pressed):
    return "PRESSED" if v == pressed else "released"

def print_pin_map():
    print("=" * 64)
    print("BAG %s: stop <= %d cm, start > %d cm, full speed at %d cm, MAX_SPEED %d%%"
          % ("BENCH" if BENCH else "REAL", STOP_DIST, START_DIST, FULL_DIST, MAX_SPEED))
    print("PIN MAP - check it against the wiring:")
    print("  Wheel 1 (DFR0601 ch 1)  PWM/A/B  GPIO 18 / 8 / 9    encoder A  GPIO 40")
    print("  Wheel 2 (DFR0601 ch 2)  PWM/A/B  GPIO 10 / 11 / 12  encoder A  GPIO 39")
    print("  Lift (MD10C)            PWM/DIR  GPIO 14 / 13       UP = DIR %d" % UP_DIR)
    print("  Lift encoder            B GPIO %d (position, stall)   A GPIO %s (printed only)"
          % (LIFT_B_PIN, LIFT_A_PIN))
    print("  UWB (UART1 115200)      ESP32 TX GPIO 47 -> J10 pin 8,  J10 pin 10 -> ESP32 RX GPIO 21")
    print("  Up button     GPIO %-2d  diagonal legs: terminal %-2d and GND   now %s"
          % (UP_PIN, UP_PIN, word(btn_up.pin.value(), BUTTON_PRESSED)))
    print("  Down button   GPIO %-2d  diagonal legs: terminal %-2d and GND   now %s"
          % (DOWN_PIN, DOWN_PIN, word(btn_down.pin.value(), BUTTON_PRESSED)))
    print("  Stop button   GPIO %-2d  diagonal legs: terminal %-2d and GND   now %s"
          % (STOP_PIN, STOP_PIN, word(btn_stop.pin.value(), BUTTON_PRESSED)))
    print("  Bottom limit  GPIO %-2d  COM -> GND, %s -> terminal %d     now %s"
          % (BOTTOM_PIN, "NO" if LIMIT_PRESSED == 0 else "NC", BOTTOM_PIN,
             word(bottom.pin.value(), LIMIT_PRESSED)))
    print("Lift: %d%% power, soft top %d pulses, max %d s per move, %.1f s up until homed"
          % (LIFT_SPEED, LIFT_TOP_COUNTS, MAX_LIFT_S, UNHOMED_UP_S))
    print("=" * 64)

# ======================= State =======================
recent = []         # last few UWB readings
dist = None         # smoothed distance (cm)
last_reading = time.ticks_ms()
armed = False
near_since = None   # ms: when the tag came within STOP_DIST (for arming)
moving = False
base = 0.0          # wheel 2 power (%)
trim = 0.0          # extra power for wheel 1 so it matches wheel 2
target = 0.0
m1 = 0.0
c1 = c2 = 0
still_steps = 0     # control steps in a row with the wheels unpowered and both encoders at 0
next_step = time.ticks_add(time.ticks_ms(), 100)
next_status = time.ticks_add(time.ticks_ms(), STATUS_MS)
next_loop_report = time.ticks_add(time.ticks_ms(), LOOP_REPORT_MS)
worst_us = 0

lift_move = None    # None, "UP" or "DOWN": the move in progress
last_move = None    # direction of the last move (for pulses while it coasts)
lift_power = 0.0
lift_start = 0      # ms: when the move started
last_pulse = 0      # ms: last encoder B pulse during the move
coast_until = 0     # ms: pulses until then still count for the last move
move_limit_ms = 0   # longest this move may run (ms)
pos = 0             # lift position (encoder B pulses above the bottom switch)
homed = False
idle_pulses = 0     # encoder B pulses while the lift was off (should stay 0)
bottom_was = False

def wheels_stopped():
    return LIFT_WHILE_DRIVING or (still_steps >= 2 and not wheels_powered())

def stop_lift(why):
    global lift_move, lift_power, coast_until
    set_lift(0)
    lift_power = 0.0
    secs = time.ticks_diff(time.ticks_ms(), lift_start) / 1000
    coast_until = time.ticks_add(time.ticks_ms(), COAST_MS)
    print("LIFT: STOP %s (%s)  ran %.1f s  position %d%s"
          % (lift_move, why, secs, pos, "" if homed else " (NOT HOMED)"))
    lift_move = None

def start_lift(name, now):
    """Up/Down pressed while the lift is off."""
    global lift_move, last_move, lift_power, lift_start, last_pulse, move_limit_ms
    if btn_stop.held():
        print("LIFT: %s refused - Stop button is held" % name)
        return
    if not wheels_stopped():
        print("LIFT: %s refused - wheels are moving (the lift only moves while they are stopped)" % name)
        return
    if name == "DOWN" and bottom.pressed:
        print("LIFT: DOWN refused - bottom switch is pressed (homed, position 0)")
        return
    if name == "UP" and homed and pos >= LIFT_TOP_COUNTS:
        print("LIFT: UP refused - at the soft top (position %d >= %d)" % (pos, LIFT_TOP_COUNTS))
        return
    move_limit_ms = MAX_LIFT_S * 1000
    if name == "UP" and not homed:
        move_limit_ms = int(UNHOMED_UP_S * 1000)
        print("NOT HOMED: press Down to home. Up limited to %.1f s" % UNHOMED_UP_S)
    set_lift_dir(UP if name == "UP" else DOWN)
    take(cnt_lb)
    take(cnt_la)
    lift_power = 0.0
    lift_start = now
    last_pulse = now
    lift_move = name
    last_move = name
    print("LIFT: %s  from position %d%s" % (name, pos, "" if homed else " (NOT HOMED)"))

def drive_mode(lost):
    if not armed:
        return "NOT-ARMED"
    if lost:
        return "NO-TAG"
    return "FOLLOW" if base > 0 else "STOPPED"

# ======================= Main loop =======================
print_pin_map()
print("NOT ARMED: stand within %d cm of the bag for %.1f s to arm" % (STOP_DIST, ARM_MS / 1000))
all_off()
read_counts()
take(cnt_lb)
take(cnt_la)
bottom.update()
bottom.update()
if bottom.pressed:
    homed = True
    bottom_was = True
    print("HOMED at start: the bottom switch is pressed, position 0")
else:
    print("NOT HOMED: press Down to home (Up is limited to %.1f s until then)" % UNHOMED_UP_S)
try:
    while True:
        t_pass = time.ticks_us()
        now = time.ticks_ms()

        # ---- UWB ----
        for d in read_distances():
            recent = (recent + [d])[-SMOOTH:]
            dist = median(recent)
            last_reading = now

        # ---- bottom switch, lift encoder, position ----
        bottom.update()
        b = take(cnt_lb)
        a = take(cnt_la)
        if b:
            if lift_move is not None or time.ticks_diff(now, coast_until) < 0:
                pos += b if last_move == "UP" else -b
                if lift_move is not None:
                    last_pulse = now
            else:
                idle_pulses += b
        if bottom.pressed:
            if not bottom_was:
                print("HOMED: bottom switch pressed, position %d -> 0" % pos)
            homed = True
            pos = 0
        bottom_was = bottom.pressed

        # ---- buttons ----
        up_ev = btn_up.update(now)
        down_ev = btn_down.update(now)
        stop_ev = btn_stop.update(now)
        if stop_ev and lift_move is not None:
            stop_lift("Stop button")
        for ev, name in ((up_ev, "UP"), (down_ev, "DOWN")):
            if not ev:
                continue
            if lift_move is None:
                start_lift(name, now)
            elif lift_move != name:
                stop_lift(name + " button (stop only)")
            # same direction again: already going

        # ---- lift stops and power (every pass, ~5 ms) ----
        if lift_move is not None:
            ran = time.ticks_diff(now, lift_start)
            if lift_move == "DOWN" and bottom.pressed:
                stop_lift("bottom switch - homed")
            elif lift_move == "UP" and homed and pos >= LIFT_TOP_COUNTS:
                stop_lift("soft top %d" % LIFT_TOP_COUNTS)
            elif ran >= move_limit_ms:
                if move_limit_ms < MAX_LIFT_S * 1000:
                    stop_lift("NOT HOMED: up limited to %.1f s - press Down to home" % UNHOMED_UP_S)
                else:
                    stop_lift("max time %d s" % MAX_LIFT_S)
            elif (STALL_CHECK and ran >= STALL_GRACE_MS
                  and time.ticks_diff(now, last_pulse) >= STALL_MS):
                stop_lift("STALL: no encoder B pulses for %d ms" % STALL_MS)
            else:
                lift_power = min(float(LIFT_SPEED), LIFT_SPEED * ran / LIFT_RAMP_MS)
                set_lift(lift_power)

        # ---- control step every 100 ms ----
        if time.ticks_diff(now, next_step) >= 0:
            next_step = time.ticks_add(next_step, 100)
            if time.ticks_diff(now, next_step) >= 0:
                next_step = time.ticks_add(now, 100)    # fell behind: do not try to catch up

            # arming (in every state)
            since_reading = time.ticks_diff(now, last_reading)
            lost = since_reading > LOST_MS
            if armed:
                if since_reading > DISARM_MS:
                    armed = False
                    moving = False
                    recent = []
                    dist = None
                    near_since = None
                    print("DISARMED: no tag for %d s. Stand within %d cm for %.1f s to arm again"
                          % (DISARM_MS // 1000, STOP_DIST, ARM_MS / 1000))
            elif not lost and dist is not None and dist <= STOP_DIST:
                if near_since is None:
                    near_since = now
                elif time.ticks_diff(now, near_since) >= ARM_MS:
                    armed = True
                    print("ARMED")
            else:
                near_since = None

            # decide the target speed
            if lost or dist is None or not armed:
                moving = False
            elif moving and dist <= STOP_DIST:
                moving = False
            elif not moving and dist > START_DIST:
                moving = True
            target = target_speed(dist) if moving else 0.0
            if lift_move is not None and not LIFT_WHILE_DRIVING:
                if moving:
                    stop_lift("wheels started moving")
                target = 0.0    # this step the wheels wait; the lift is off from the next step

            # ramp the base speed toward the target
            if target > base:
                base = min(target, base + RAMP_UP)
                if base < MIN_SPEED:
                    base = MIN_SPEED            # start straight at a speed that moves
            else:
                base = max(target, base - RAMP_DOWN)
                if target == 0 and base < MIN_SPEED:
                    base = 0.0                  # below this the wheels barely turn

            # match wheel 1 to wheel 2 with the encoders
            c1, c2 = read_counts()
            if base > 0 and c1 > 0 and c2 > 0:
                step = max(-MAX_STEP, min(MAX_STEP, GAIN * (c2 - c1)))
                trim = max(-MAX_TRIM, min(MAX_TRIM, trim + step))
            m1 = max(0, min(100, base + trim)) if base > 0 else 0
            motor1(m1)
            motor2(base)
            still_steps = still_steps + 1 if (base == 0 and c1 == 0 and c2 == 0) else 0

        # ---- status line every 0.3 s ----
        if time.ticks_diff(now, next_status) >= 0:
            next_status = time.ticks_add(now, STATUS_MS)
            lost = time.ticks_diff(now, last_reading) > LOST_MS
            print("%-9s %s | dist %s tgt %2d base %4.1f | M1 %3d M2 %3d p1 %4.1f | lift %-4s pos %d %s"
                  % (drive_mode(lost), "ARMED" if armed else "-----",
                     "---" if (dist is None or lost) else "%d" % dist, round(target), base,
                     c1, c2, m1, lift_move or "OFF", pos, "homed" if homed else "NOT-HOMED"))

        # ---- worst loop time every 5 s ----
        if time.ticks_diff(now, next_loop_report) >= 0:
            next_loop_report = time.ticks_add(now, LOOP_REPORT_MS)
            msg = "loop: worst pass %.1f ms in the last %d s" % (worst_us / 1000, LOOP_REPORT_MS // 1000)
            if idle_pulses:
                msg += "  | WARNING: %d lift pulses while the lift was off (position may be off)" % idle_pulses
                idle_pulses = 0
            print(msg)
            worst_us = 0

        worst_us = max(worst_us, time.ticks_diff(time.ticks_us(), t_pass))
        time.sleep_ms(5)

finally:
    all_off()
    uart.deinit()
    print("Motors stopped (wheels and lift)")
