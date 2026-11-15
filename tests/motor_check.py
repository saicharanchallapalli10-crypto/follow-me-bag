from machine import Pin, PWM
import machine
import time

TEST_SPEED = 50     # % power for each test
RUN_TIME = 3        # seconds per test

# ---------------- Motors ----------------
pwm1 = PWM(Pin(18), freq=1000, duty_u16=0)
ina1 = Pin(8, Pin.OUT, value=0)
inb1 = Pin(9, Pin.OUT, value=0)
pwm2 = PWM(Pin(10), freq=1000, duty_u16=0)
ina2 = Pin(11, Pin.OUT, value=0)
inb2 = Pin(12, Pin.OUT, value=0)

def set_motor(pwm, ina, inb, speed):
    speed = max(-100, min(100, speed))
    ina.value(1 if speed > 0 else 0)
    inb.value(1 if speed < 0 else 0)
    pwm.duty_u16(int(abs(speed) * 655))

def motor1(speed):
    set_motor(pwm1, ina1, inb1, speed)

def motor2(speed):
    set_motor(pwm2, ina2, inb2, speed)

# ---------------- Encoders (motor 1 on GPIO 40, motor 2 on GPIO 39) ----------------
enc1_pin = Pin(40, Pin.IN, Pin.PULL_UP)
enc2_pin = Pin(39, Pin.IN, Pin.PULL_UP)
try:
    from machine import Counter
    cnt1 = Counter(0, enc1_pin, edge=Counter.RISING, filter_ns=10000)
    cnt2 = Counter(1, enc2_pin, edge=Counter.RISING, filter_ns=10000)

    def read_counts():
        c1, c2 = cnt1.value(), cnt2.value()
        cnt1.value(0)
        cnt2.value(0)
        return c1, c2
except Exception:
    count = [0, 0]
    enc1_pin.irq(trigger=Pin.IRQ_RISING, handler=lambda p: count.__setitem__(0, count[0] + 1))
    enc2_pin.irq(trigger=Pin.IRQ_RISING, handler=lambda p: count.__setitem__(1, count[1] + 1))

    def read_counts():
        state = machine.disable_irq()
        c1, c2 = count[0], count[1]
        count[0] = count[1] = 0
        machine.enable_irq(state)
        return c1, c2

def run_test(name, s1, s2):
    print()
    print("=== " + name + " ===")
    for s in range(0, 101, 20):                 # gentle ramp up
        motor1(s1 * s / 100)
        motor2(s2 * s / 100)
        time.sleep(0.1)
    read_counts()
    tot1 = tot2 = 0
    for k in range(RUN_TIME * 2):
        time.sleep(0.5)
        c1, c2 = read_counts()
        tot1 += c1
        tot2 += c2
        print("  enc1 (motor 1):", c1, "   enc2 (motor 2):", c2)
    motor1(0)
    motor2(0)
    time.sleep(1.5)
    return tot1, tot2

def verdict(name, tot1, tot2, expect1, expect2):
    ok1 = (tot1 > 50) == expect1
    ok2 = (tot2 > 50) == expect2
    status = "OK" if ok1 and ok2 else "CHECK THIS"
    print("  ->", status, "  (enc1 total", tot1, ", enc2 total", tot2, ")")
    return status == "OK"

results = []
try:
    print("Motor check: lift the wheels off the ground. Each test runs", RUN_TIME, "s.")
    t = run_test("Motor 1 (left) FORWARD - only the left wheel should spin", TEST_SPEED, 0)
    results.append(verdict("M1 fwd", *t, True, False))
    t = run_test("Motor 1 (left) REVERSE - left wheel, other direction", -TEST_SPEED, 0)
    results.append(verdict("M1 rev", *t, True, False))
    t = run_test("Motor 2 (right) FORWARD - only the right wheel should spin", 0, TEST_SPEED)
    results.append(verdict("M2 fwd", *t, False, True))
    t = run_test("Motor 2 (right) REVERSE - right wheel, other direction", 0, -TEST_SPEED)
    results.append(verdict("M2 rev", *t, False, True))
    t = run_test("BOTH FORWARD - both wheels, same direction", TEST_SPEED, TEST_SPEED)
    results.append(verdict("Both fwd", *t, True, True))
    print()
    print("ALL TESTS PASSED" if all(results) else "Some tests need checking - see CHECK THIS above")
finally:
    motor1(0)
    motor2(0)
    print("Motors stopped")
