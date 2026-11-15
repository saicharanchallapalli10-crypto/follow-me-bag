# Harmless stop test: no motors, no pins.
# Prints a counter every 0.5 s forever. When stopped with Ctrl-C (or the STOP task)
# it must print "finally ran", the same way the motor programs turn the motors off.
import time

n = 0
try:
    while True:
        print("loop_test count:", n)
        n += 1
        time.sleep(0.5)
finally:
    print("finally ran")
