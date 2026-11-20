# Follow-me bag: project context for Claude Code

Forge (Northeastern) team project: an autonomous bag that follows a person. The owner of this
repo (SaiCharan, 2nd-year EE) handles the electronics, UWB tracking and drivetrain code.
Current team scope: front-wheel drive, straight-line following (distance only, no steering yet).

Status: the drivetrain and UWB distance-following work on the bench (wheels in the air).
`follow_me_bench.py` was confirmed working. Next: mount on the bag and test on the ground.

## Hardware

- MCU: ESP32-S3 DevKit (WROOM-1), MicroPython v1.29.0. `machine.Counter` (hardware pulse counter with
  `filter_ns`) is available and in use.
- Motor driver: DFRobot DFR0601 (dual 12A). Wheel motors: 2x DFRobot FIT0186 (12V, Hall encoders).
- Power: 12V LiFePO4 -> 15A fuse -> switch -> 12V bus (DFR0601, MD10C, UBEC). Adafruit 1385 UBEC 12V->5V
  feeds the breadboard rails.
- UWB: 2x Qorvo DWM3001CDK. Bag board = initiator wired to the ESP32. Tag = responder carried by the person.
- Lift: FIT0403 motor + Cytron MD10C: GPIO 14 -> MD10C PWM, GPIO 13 -> MD10C DIR; MD10C GND -> ESP32 G.
  Lift encoder A (yellow) GPIO 42, B (white) GPIO 38, each through a 10k/20k divider (wired and tested). Hardware counters 2 and 3
  (wheels use 0 and 1). Which DIR value is UP is NOT confirmed yet (`LIFT_UP_DIR` = 0 placeholder).

## Pin map (confirmed on hardware)

| Function | ESP32 pin | Other end |
|---|---|---|
| Motor 1 (left) PWM / A / B | 18 / 8 / 9 | DFR0601 P1 / A1 / B1 |
| Motor 2 (right) PWM / A / B | 10 / 11 / 12 | DFR0601 P2 / A2 / B2 |
| Motor 1 encoder A | **40** | yellow wire via 10k/20k divider + 1 nF to GND |
| Motor 2 encoder A | **39** | yellow wire via 10k/20k divider + 1 nF to GND |
| Lift PWM / DIR | 14 / 13 | MD10C PWM / DIR |
| Lift encoder A / B | **42** / **38** | yellow / white, each via 10k/20k divider (tested) |
| UWB sensor TX -> ESP32 RX | 21 | DWM3001CDK J10 pin 10 |
| ESP32 TX -> UWB sensor RX | 47 | DWM3001CDK J10 pin 8 |

- DFR0601 header VCC (both pins tied) -> ESP32 3V3. GND (both tied) -> ground. A 5V rail section on the
  breadboard is dead (cause unknown), so do not move VCC there.
- J10 pin 2 -> 5V rail (UBEC), J10 pin 6 -> ground.
- Wheel encoder B channels (white wires) are NOT confirmed and not used in code. (Lift encoder B on GPIO 38 is tested.)
- The ESP32 G pin MUST be on the shared ground. Missing ground caused most early bugs.

## UWB setup (already done, saved on the boards)

- Bag board: Qorvo CLI firmware (SDK 1.1.1), configured with `setapp initf`, `save`, `UART 1`, `save`.
  It starts ranging at power-up and streams results out J10 at **115200 baud**. After `UART 1` its USB
  console stops answering; that is expected.
- Tag: Qorvo "USB_Workaround" CLI firmware (needed for power-bank operation), `setapp respf`, `save`.
  Powered from a USB power bank through **J9**.
- Output format (cm; small negative values near 0 cm are normal):
  `[mac_address=0x0001, status="SUCCESS", distance[cm]=87]}`
  Parse after `distance[cm]=` and stop at the NEXT `]` after the number (the first `]` is inside `[cm]`).

## Files

- `follow_me.py`: main program. Median-of-5 UWB distance -> target speed; stop <= 100 cm, start > 115 cm,
  35% at start up to 80% at >= 300 cm; ramp +3%/-10% per 0.1 s; stops if no reading for 1 s;
  motor 2 = base power, motor 1 = base + trim from encoder count difference (GAIN 0.03, MAX_STEP 2, MAX_TRIM 20).
  Lift on terminal keys u / d / s (non-blocking stdin via select.poll): 40% power, 1 s per press, max 4 s,
  stall stop after 3 zero reads on encoder A. INTERLOCK: wheels and lift are never powered together.
  Modes DRIVE -> STOP_WHEELS (ramp to 0, wait for both wheel encoders at 0, max 1.5 s) -> LIFT -> SETTLE (0.3 s)
  -> DRIVE. set_motor/set_lift check the other motors' real PWM duty and on a conflict cut all motors and raise.
  Logic was checked on the Mac in a fake-hardware simulation only (2026-11-18), not on hardware yet.
- `follow_me_bench.py`: same with 30 / 40 / 100 cm for bench tests (keep it identical apart from those 3 lines).
- `lift_web.py`: standalone lift test, phone control. ESP32 runs a Wi-Fi access point "BagLift" / "followme123"
  (network.WLAN AP_IF, WPA2) and an asyncio web server on port 80 at http://192.168.4.1: hold-to-run UP / DOWN
  (page repeats the command every 150 ms, sends stop on release / page hidden; commands carry a page id + sequence
  number so out-of-order requests are dropped) and STOP. Lift loop every 50 ms: stops if no UP/DOWN for 500 ms
  (TIMEOUT_MS), ramps up 10%/0.1 s to 40% (LIFT_SPEED), stops immediately, changes DIR only at 0 power.
  Stall stop on encoder A (GPIO 42, Counter 2; STALL_CHECK) and optional limit switches (TOP/BOTTOM_LIMIT_PIN,
  default None; pull-up to GND, LIMIT_PRESSED = 1 for NC). Stall/limit stops latch until the button is released.
  Wheels held off. Terminal prints `LIFT: UP` / `LIFT: DOWN` / `LIFT: STOP (<reason>)`. finally: motors off, AP off.
  Settings block at the top (UP_DIR = 0 placeholder, same meaning as LIFT_UP_DIR). Runs with the normal Run task,
  stops with Ctrl+C / STOP task. Written 2026-11-19 and checked on the Mac only (CPython + fake machine/network,
  real HTTP requests); NOT run on hardware yet.
- `tests/`: lift_test_encoder.py (lift DIR 0 then DIR 1, counts A/B, wheels held off), motor_check.py, motor_match.py, uwb_distance.py, uwb_test.py, uwb_send_commands.py, uwb_baud_scan.py,
  loop_test.py (harmless counter for stop tests).
- `tools/esp32.py`: host-side run/stop wrapper (Mac; Windows branches untested). `run` uses mpremote's
  SerialTransport (same upload as `mpremote run`, which never forwards keyboard input) and forwards typed lines
  to the program's stdin. The new `run` was checked against a fake board on a pty, not yet on the ESP32.
  Not uploaded to the board.

## Running code (macOS)

- mpremote is installed at `~/Library/Python/3.9/bin` (added to PATH in ~/.zprofile). `python3 -m mpremote` also works.
- Ports: ESP32 = `/dev/cu.usbserial-130` (CP2102N; number depends on which Mac USB port).
  Tag = `/dev/cu.usbmodemE3C6089B3B5D1`. Bag UWB board = `/dev/cu.usbmodemFD1995DCFB7D1`.
  Check with `mpremote devs`. Always pass the ESP32 port explicitly; auto-connect may pick a UWB board.
- Run: `python3 tools/esp32.py run <file>.py` (VS Code: Cmd+Shift+B). Stop: Ctrl+C in that terminal, or
  `python3 tools/esp32.py stop` (VS Code task "ESP32: STOP program (motors off)", no port prompt).
  Default port /dev/cu.usbserial-130 (override with `--port` or `$ESP32_PORT`; falls back to the only usbserial port).
- Why: plain `mpremote run` exits on Ctrl+C (`sys.exit(1)` in mpremote's commands.py) without sending Ctrl-C
  to the board, so the program and motors keep running. Never run motor programs with plain `mpremote run`.
  `tools/esp32.py stop` kills local mpremote/run processes, sends ONE Ctrl-C (a second one too soon
  could cut the finally block short), waits for the prompt, then checks the board is idle at `>>>`.
  Verified on hardware 2026-11-15 with `tests/loop_test.py` (harmless; use it, not a motor script, to test stopping).
- Testing note: background jobs in a non-interactive shell ignore SIGINT, so `cmd & kill -INT` will not reproduce
  a terminal Ctrl+C. Start the child with SIGINT reset to default and signal its process group instead.
- `.vscode/tasks.json` has Run (Cmd+Shift+B), STOP, upload-as-main.py, REPL and list tasks. The STOP keyboard
  shortcut is user-level (keybindings.json); setup steps are in README.
- Close Thonny before using mpremote; only one program can hold a serial port.
- UWB board consoles: `screen <port> 115200`, exit with Ctrl-A, K, Y (closing the window leaves screen running and blocks the port).

## Rules for working on this project

- Safety first: never start a motor program without the user confirming the wheels are off the ground
  (or the bag is in an open area with someone at the power switch). Every motor program must wrap its
  loop in try/finally that sets both motors to 0. Ramp speed changes. Do not raise MAX_SPEED above 80.
- Do not upload anything as `main.py` (auto-run at power-up) without asking first.
- Because motor programs never exit on their own, prefer letting the user run them; if you run one, use a
  bounded run and always run `python3 tools/esp32.py stop` afterwards.
- Change one thing at a time from the last working version, and ask for the program output before guessing.
  Check power and ground before suspecting code.
- The user is on a Mac, prefers short step-by-step instructions and complete files rather than fragments.

## Open items

- Ground test on the bag; start with MAX_SPEED around 50.
- Optional arming step: don't move after power-up until the tag has first been seen within STOP_DIST.
- Confirm the tag keeps ranging on the power bank over long runs (some power banks shut off at low current).
- Lift: confirm which DIR is UP with tests/lift_test_encoder.py, set LIFT_UP_DIR in both follow files.
  Test the new esp32.py run (typing reaches the board) with tests/loop_test.py, then the lift keys.
- Lift website: first hardware test of lift_web.py without the MD10C connected (STALL_CHECK = False, watch for
  LIFT: UP / STOP / timeout), then with the motor; set UP_DIR to match LIFT_UP_DIR; add limit switches.
- MERGE PLAN: the ESP32 runs one program at a time, so follow_me.py and lift_web.py are separate tests for now.
  Merge them into one asyncio program (follow-me loop + web server + lift loop, keeping the wheel/lift interlock
  from follow_me.py) that becomes main.py (ask before uploading as main.py). Not written yet.
- Later: two anchors for steering; ultrasonic/ToF for obstacles and stairs.
