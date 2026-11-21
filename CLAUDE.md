# Follow-me bag: project context for Claude Code

Forge (Northeastern) team project: an autonomous bag that follows a person. The owner of this
repo (SaiCharan, 2nd-year EE) handles the electronics, UWB tracking and drivetrain code.
Current team scope: front-wheel drive, straight-line following (distance only, no steering yet).

Status: the drivetrain and UWB distance-following work on the bench (wheels in the air), re-confirmed on the
new ESP32-S3 + Freenove breakout on 2026-11-20.
`follow_me_bench.py` was confirmed working. Next: mount on the bag and test on the ground.

## Hardware

- MCU (replaced 2026-11-20, the old CP2102N DevKit died): ESP32-S3-N8R2 DevKitC-style clone (8 MB flash,
  2 MB PSRAM, chip rev v0.2, MAC 28:37:2f:f8:ba:9c), MicroPython v1.29.0 ESP32_GENERIC_S3, 160 MHz.
  `machine.Counter` (hardware pulse counter with `filter_ns`) is available and in use.
  Two USB-C ports: "COM" = WCH CH343 (1a86:55d3, `/dev/cu.usbmodem595B0699471`) = the ONLY port with the REPL.
  "USB" = native USB Serial/JTAG (303a:1001, `/dev/cu.usbmodem101`): with only that port plugged in the chip
  always starts in download mode (even after RST without BOOT; boot:0x0), so it is for flashing only
  (esptool stub + flash work there; on COM, large esptool transfers fail).
  RGB LED is on GPIO 48 (mcu_check 2026-11-20: green lit, blue on GPIO 38 did not), so GPIO 38 is free for lift encoder B.
  Wi-Fi activation reset the board (rst:0x1 POWERON, 3 of 3 tries) when powered from the Mac's USB port:
  supply dip. Not yet tried on another cable/hub or the UBEC 5V rail. Matters for lift_web.py.
  SAME on the Freenove breakout, native USB to the Mac (2026-11-20, 3 of 3, two different cables): lift_web.py and a Wi-Fi-only test
  (scratch wifi_only.py) both lost the board at `ap.active(True)` ("AP object made" printed, then
  OSError 6 'Device not configured' = USB device gone; uptime afterwards ~20 s = chip rebooted). The API calls
  themselves are fine. Also fails on a POWERED USB hub (4th try). machine.reset_cause() read with `mp resume exec` right after
  the reboot = 1 (PWRON/brownout), not a panic/WDT. So a real supply dip on the board side (load on the
  breakout's 5V/3V3 rails, e.g. the breadboard 5V rail with the UWB board, or a weak 3V3 regulator), not the
  USB source. Next: test with nothing on the breakout's 5V/3V3 terminals; bulk cap 470-1000 uF on 5V/GND.
  2026-11-20: board moved onto a Freenove ESP32-S3 breakout (no wiring file in the repo yet). In the breakout the
  "USB" port runs MicroPython: native USB CDC 303a:4001, `/dev/cu.usbmodem101`. Plain mpremote is reliable there
  (15.5 KB run OK, no pacing needed); esp32.py auto-detect prefers it over the COM port.
- One-motor test 2026-11-20 on the new board/breakout (tests/test_each_channel.py: channel 1 then channel 2,
  30% fwd/rev, never both, ~9.6 s; tests/test_one_motor.py = channel 2 only). The "wheel 1" motor is on DFR0601
  CHANNEL 2 (GPIO 10/11/12). WORKING on the 7th run: its encoder (yellow, via divider) is on **GPIO 39**
  (GPIO 40 stayed 0). At 29% duty: ~230 rising edges per 0.25 s (~920/s); forward total 1347, reverse 1349
  (symmetric). At 80% (tests/test_one_motor.py, 1 s ramps, 1.5 s hold): ~627 per 0.25 s forward (~2500/s),
  ~622 reverse; totals 6235 / 6184. Channel 1 (no motor) correctly gave 0 counts. This matches the pin map (channel 2 encoder = 39).
  Channel 1 with the second wheel motor (tests/test_one_motor.py, CHANNEL = 1, 30%): encoder on **GPIO 40**
  (GPIO 39 stayed 0). ~230 per 0.25 s forward, ~224 reverse; totals 2234 / 2176. Matches the pin map
  (channel 1 encoder = 40) and matches the channel 2 motor at 30% (~230). Both wheel channels now confirmed.
  The first six runs gave no movement: the DFR0601 was unpowered at first; the final fix was not identified
  (user reseated jumpers between breakout and DFR0601; nothing reported changed before the working run, so
  suspect a loose connection). Thonny can leave the board where Ctrl-C gets no prompt; esp32.py stop recovers
  it. Quit Thonny before using the tools.
- Motor driver: DFRobot DFR0601 (dual 12A). Wheel motors: 2x DFRobot FIT0186 (12V, Hall encoders).
- Power: 12V LiFePO4 -> 15A fuse -> switch -> 12V bus (DFR0601, MD10C, UBEC). Adafruit 1385 UBEC 12V->5V
  feeds the breadboard rails.
- UWB: 2x Qorvo DWM3001CDK. Bag board = initiator wired to the ESP32. Tag = responder carried by the person.
- Lift: FIT0403 motor + Cytron MD10C: GPIO 14 -> MD10C PWM, GPIO 13 -> MD10C DIR; MD10C GND -> ESP32 G.
  Lift encoder A (yellow) GPIO 42, B (white) GPIO 38, each through a 10k/20k divider (wired and tested). Hardware counters 2 and 3
  (wheels use 0 and 1). Which DIR value is UP is NOT confirmed yet (`LIFT_UP_DIR` = 0 placeholder).
  2026-11-20, new board: tests/lift_test_encoder.py ran (40%, ~1 s per direction, both wheel channels held off):
  motor runs, encoder A and B both count and agree (~123 per 0.1 s each, ~1230/s). Totals DIR 0: A 1747 B 1749,
  DIR 1: A 1753 B 1754. Nearly identical speeds both ways, and the user could not see the direction, so it is
  NOT yet proven that DIR (GPIO 13) actually reverses the motor. Rising-edge counts carry no direction.
  Quadrature direction is available: this firmware's machine.Counter (frozen machine.py) rejects a Pin for
  `direction`, but `esp32.PCNT(2, pin=A, rising=esp32.PCNT.INCREMENT, mode_pin=B, mode_low=esp32.PCNT.REVERSE,
  filter=1000)` works (checked with inputs only); its count goes up one way and down the other.
  Rerun on the screw-terminal setup (after the bench test): same result, no stall, A/B agree (~124 per 0.1 s);
  totals DIR 0: A 1781 B 1779, DIR 1: A 1767 B 1767. User again could not tell the direction.
  DIR PROVEN with tests/lift_direction.py (quadrature count via esp32.PCNT, 40%, ~1 s each way): DIR 0 = -1771,
  DIR 1 = +1765 (opposite signs, same speed ~124 per 0.1 s). So GPIO 13 reverses the lift; negative count = DIR 0,
  positive = DIR 1. Which of them is UP is still not seen (LIFT_UP_DIR stays 0 placeholder).
  Find-UP run (lift_direction.py WATCH_DIR = 0: 30%, 2.5 s, then back): DIR 0 = -2532, DIR 1 = +2572 (~90 per
  0.1 s at 30%), ended about where it started, no stall. User saw the motor turn COUNTER-CLOCKWISE in the second
  half, so DIR 1 = CCW (positive count), DIR 0 = CW (negative count), viewing direction not recorded.
  The scissor lift itself is NOT attached yet (2026-11-20): these were the lift motor's gears only. UP cannot be
  known until the lift is mounted: then run tests/lift_direction.py (WATCH_DIR = 0) with the lift at
  mid-height, see whether DIR 0 (CW) raises or lowers it, and set LIFT_UP_DIR (follow files) and UP_DIR (lift_web.py).
  UP FOUND 2026-11-20: DIR 0 = UP, DIR 1 = DOWN (tests/lift_buttons.py: the Up button, confirmed on GPIO 4,
  drove the lift DOWN twice with DIR 1). An earlier report from lift_cw/lift_ccw said the opposite (CCW = up);
  that was wrong. LIFT_UP_DIR = 0 (follow files), UP_DIR = 0 (lift_web.py, bag_main*.py, lift_buttons.py).
  At 80% encoder B gives ~2350-2500 pulses/s. A DIR 1 run stalled after ~8600 pulses (an end of travel).
  Buttons now: Up GPIO 4, Down GPIO 17 (GPIO 5 dropped 2026-11-20), Stop GPIO 6, bottom limit GPIO 7.
  CONFIRMED 2026-11-20: tests/lift_buttons.py (80%, Up/Down/Stop buttons, stall + bottom switch + 8 s stops)
  works: Up raises, Down lowers, Stop stops.

## Pin map (confirmed on hardware)

| Function | ESP32 pin | Other end |
|---|---|---|
| Motor 1 (left) PWM / A / B | 18 / 8 / 9 | DFR0601 P1 / A1 / B1 |
| Motor 2 (right) PWM / A / B | 10 / 11 / 12 | DFR0601 P2 / A2 / B2 |
| Motor 1 encoder A | **40** | yellow wire via 10k/20k divider + 1 nF to GND (re-confirmed on new board 2026-11-20: channel 1 motor) |
| Motor 2 encoder A | **39** | yellow wire via 10k/20k divider + 1 nF to GND (re-confirmed on new board 2026-11-20: channel 2 motor) |
| Lift PWM / DIR | 14 / 13 | MD10C PWM / DIR |
| Lift encoder A / B | **42** / **38** | yellow / white, each via 10k/20k divider (tested) |
| UWB sensor TX -> ESP32 RX | 21 | DWM3001CDK J10 pin 10 |
| ESP32 TX -> UWB sensor RX | 47 | DWM3001CDK J10 pin 8 |
| Up button | **4** | 4-leg tactile, diagonal legs: terminal 4 and GND (tested 2026-11-20) |
| Down button | **17** | diagonal legs: terminal 17 and GND (tested; GPIO 5 dropped, its button/wire never responded) |
| Stop button | **6** | diagonal legs: terminal 6 and GND (works in lift_buttons.py) |
| Bottom limit switch | **7** | COM -> GND, NO -> 7 (pressed = 0, LIMIT_PRESSED setting); at the LOWEST allowed height. No top switch. Not tested alone yet |

- Current setup (2026-11-20): ESP32-S3-N8R2 in the Freenove breakout, all connections on its screw terminals.
  DFR0601 P1/A1/B1 = GPIO 18/8/9 (channel 1), P2/A2/B2 = GPIO 10/11/12 (channel 2). DFR0601 VCC (both pins
  jumpered) -> ESP32 3V3 only; DFR0601 GND (both jumpered) -> breadboard - rail; ESP32 GND -> breadboard - rail.
  Wheel encoders (yellow via 10k/20k dividers) on GPIO 39 / 40, white wires unused. UWB bag board J10:
  pin 8 <- GPIO 47, pin 10 -> GPIO 21, pin 2 -> 5V rail, pin 6 -> GND; auto-starts ranging (initf, UART 1 saved).
  Tag on a power bank via J9, ranges on its own.
  Pairing check on this setup (tests/test_each_channel.py, 30%): BOTH wheels turned, but channel 1 gave 0 counts
  on GPIO 39 and 40, and channel 2 gave IDENTICAL counts on BOTH 39 and 40 (1317/1316 fwd, 1338/1338 rev).
  GPIO 39 and 40 are not shorted to each other at the board (driving one does not move the other), so both
  dividers are fed from the channel 2 motor's yellow wire, and the channel 1 encoder (yellow wire or its 5V/GND)
  reaches neither. Wiring must be fixed before follow_me_bench.py (speed matching would see equal counts).
  enc1_pin = 40 / enc2_pin = 39 left unchanged in the code (matched the earlier per-channel tests).
  UWB on this setup: tests/uwb_distance.py gave 54 SUCCESS readings in ~10 s (~5 Hz), 28-58 cm. Parser OK.
  SAFETY 2026-11-20: running tests/test_one_motor.py on CHANNEL 1 alone, the LIFT motor ran at the same time
  as motor 1 (user report). That test did not configure GPIO 14/13, so the MD10C PWM input was floating
  (likely picks up the channel 1 PWM), or GPIO 18 is also wired to MD10C PWM. Channel 1 encoder again 0 on 39/40.
  Fix: every wheel test now holds lift PWM 14 = 0 / DIR 13 = 0 (test_one_motor, test_each_channel, motor_check,
  motor_match), like lift_test_encoder holds the wheels. RULE: every program must drive ALL motor pins
  (wheels + lift) to 0 at the start. Consider a 10k pull-down on MD10C PWM to GND (keeps the lift off at boot).
  CONFIRMED: rerun of channel 1 with the lift held off: lift stayed still, and channel 1's encoder counted on
  GPIO 40 only (~224 per 0.25 s, totals 2204 / 2173), GPIO 39 = 0. So the floating lift PWM was the cause, and
  the missing/doubled encoder counts in the earlier runs went away with it (exact mechanism not identified;
  likely the lift running alongside disturbed the encoder signals).
  PAIRING CONFIRMED on the screw-terminal setup (test_one_motor.py, lift held off, 30%): channel 1 -> GPIO 40 only
  (~224 per 0.25 s), channel 2 -> GPIO 39 only (~224 fwd / ~228 rev; totals 2204 / 2232). Matches enc1_pin = 40,
  enc2_pin = 39 in follow_me.py and follow_me_bench.py, so no code change. Both motors run at the same speed.
  BENCH TEST PASSED on the new setup (follow_me_bench.py, ~75 s, stopped with esp32.py stop -> "Motors stopped"):
  never moved at <= 30 cm, never stayed still with target > 0, started past 40 cm (4 starts), stopped at
  <= 30 cm (4 stops), reached 80% beyond 100 cm (max 129 cm), slowed smoothly coming back, no NO TAG, lift
  stayed off. Encoders while moving: |M1-M2| mean 0.7, max 4 counts per 0.1 s (max 6%); trim stayed
  -0.6..+0.1 %, so the motors are naturally matched. Counts per 0.1 s by power: ~110 @30-40%, 131 @40%,
  167 @50%, 196 @60%, 231 @70%, 245 @80%.
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

- `bag_main.py` (BENCH = False: 100/115/300 cm, MAX_SPEED 50) and `bag_main_bench.py` (identical except line 1
  BENCH = True: 30/40/100 cm, MAX_SPEED 80): THE bag program, written 2026-11-20. One loop polls UART, buttons,
  bottom switch and lift encoder every ~5 ms; follow-me control step every 100 ms (same logic as follow_me.py).
  Arming: wheels stay still until the tag is within STOP_DIST for 1 s ("ARMED"); no reading for 3 s -> DISARMED.
  Lift: Up 4 / Down 17 / Stop 6, 30 ms debounce, act on press, held-at-power-up ignored until released.
  LIFT_SPEED 80, ramp 0.5 s, stop immediate. Position = encoder B (GPIO 38, Counter 3) pulses, + up / - down by
  the DIR we set (pulses in the 0.3 s coast after a stop count too; pulses while off are warned about).
  Bottom switch pressed = homed, pos 0. DOWN stops: bottom switch, Stop, Up (stop only), stall, MAX_LIFT_S 8.
  UP stops: pos >= LIFT_TOP_COUNTS (PLACEHOLDER 3000, calibrate), Stop, Down, stall, MAX_LIFT_S. Not homed ->
  each Up move limited to UNHOMED_UP_S 1.5 s (~3000 pulses at 80%). Stall = no B pulse for 0.3 s after the first
  0.5 s. Refuses Down on the switch, Up at the soft top, anything while Stop is held, and (LIFT_WHILE_DRIVING =
  False) any lift move unless the wheels are unpowered with 0 counts for 2 steps; if the wheels want to move
  while the lift runs, the lift stops ("wheels started moving"). set_motor/set_lift interlock as follow_me.py.
  Prints the pin map with live input states at start, a status line every 0.3 s, worst loop time every 5 s.
  Checked in a Mac fake-hardware simulation only (every stop reason, arming, interlock); NOT run on hardware yet.
- `tests/lift_calibrate.py`: homes on the bottom switch (Down), Up refused until homed, no soft top, prints the
  position every 0.25 s while moving; same counting as bag_main. For finding LIFT_TOP_COUNTS. Not run yet.
- `tests/lift_buttons.py`: lift on Up/Down/Stop only (80%, stall/bottom switch/8 s stops, no homing). WORKS.
- `tests/lift_cw.py` (DIR 0 = UP) / `tests/lift_ccw.py` (DIR 1 = DOWN): 80% until Stop, stall, bottom switch, 30 s.
  `tests/lift_80.py`: 80% ~2 s one way.
- `tests/button_check.py` (all four inputs, ONLY_GPIO setting), `tests/button4/5/6/17.py` (one GPIO, 20 s),
  `tests/pin_finder.py` (all free GPIOs 30 s), `tests/limit_switch.py` (GPIO 7). No motors in any of them.
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
- `tests/mcu_check.py`: new-board check, nothing wired (firmware, flash, PSRAM, Counter on GPIO 40 input, RGB LED
  green on 48 then blue on 38, Wi-Fi scan last because it can reset the board on weak USB power). Ends by itself.
- `tests/`: lift_test_encoder.py (lift DIR 0 then DIR 1, counts A/B, wheels held off), motor_check.py, motor_match.py, uwb_distance.py, uwb_test.py, uwb_send_commands.py, uwb_baud_scan.py,
  loop_test.py (harmless counter for stop tests).
- `tools/esp32.py`: host-side run/stop wrapper (Mac; Windows branches untested). `run` uses mpremote's
  SerialTransport (same upload as `mpremote run`, which never forwards keyboard input) and forwards typed lines
  to the program's stdin. Also `mp` (paced mpremote passthrough) and `port`. `run` (output, finishing, reboot
  detection) and `stop` verified on the new ESP32 2026-11-20; typed-line forwarding to stdin not yet tested on
  hardware. Not uploaded to the board.

## Running code (macOS)

- mpremote is installed at `~/Library/Python/3.9/bin` (added to PATH in ~/.zprofile). `python3 -m mpremote` also works.
- Ports: ESP32 = `/dev/cu.usbmodem595B0699471` (CH343 "COM" port; the name comes from the chip serial, so it
  does not change with the Mac USB port). Tag = `/dev/cu.usbmodemE3C6089B3B5D1`.
  Bag UWB board = `/dev/cu.usbmodemFD1995DCFB7D1`. All are usbmodem now, so never rely on mpremote auto-connect.
- `tools/esp32.py` auto-detects the ESP32 by USB id (WCH 1a86:55d3/55d4, else CP210x; never UWB boards;
  says "move the cable to COM" if only 303a:1001 is seen). Override with `--port` or `$ESP32_PORT`.
  `python3 tools/esp32.py port` prints it.
- COM-port data loss (found 2026-11-20): the CH343 + macOS driver drops host->board bytes whenever a write is
  queued while earlier bytes are still going out at 115200. Plain `mpremote run` of a 3 KB file failed 10/10
  (random SyntaxError/NameError); `mpremote cp` happened to survive (small exec per chunk). Raw-paste window is
  128 and the board acks correctly, so it is not the firmware (esptool's ROM loader fails the same way).
  Fix in esp32.py: every serial write is split into 64-byte pieces, each sent only after the previous one has
  had time to go out (10 bits/byte at 115200, +25%). Verified: 15.5 KB run 3/3, cp of follow_me.py matches SHA-256.
  Pacing is on for WCH ports (ESP32_PACE=1/0 forces it on/off). Use `python3 tools/esp32.py mp <mpremote args>`
  (= `mpremote connect <port> ...` with pacing) instead of plain mpremote for anything bigger than a short exec.
  Untried alternative: WCH's own macOS CH34x driver (would show the port as /dev/cu.wchusbserial*).
- DTR/RTS on COM: the board resets when DTR != RTS (classic two-transistor auto-reset). DTR=RTS=1 never resets it
  (verified by uptime across connections); pyserial/mpremote default open and mpremote's close are safe.
  pyserial with dtr=rts=False set before open DOES reset it (macOS raises both on open, pyserial clears DTR first).
- `esp32.py run` now exits with a WARNING if it sees the ROM banner `ESP-ROM:` (board rebooted mid-program).
- Run: `python3 tools/esp32.py run <file>.py` (VS Code: Cmd+Shift+B). Stop: Ctrl+C in that terminal, or
  `python3 tools/esp32.py stop` (VS Code task "ESP32: STOP program (motors off)"). No VS Code task asks for a
  port any more; upload/remove main.py, REPL and ls tasks go through `esp32.py mp`.
  Run and stop verified on the new board 2026-11-20 with tests/loop_test.py (`finally ran`, idle at >>>).
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
  Keep test scripts SIMPLE when asked ("don't overcomplicate"): small single-purpose files they run themselves.
- README.md has Mac + Windows setup and Claude Code instructions; keep both in step when commands change.

## Open items

- bag_main test plan (user runs, wheels off the ground): 1. buttons (done except the bottom switch alone);
  2. bag_main_bench.py with the lift motor unplugged (arming, following, lost-tag stop, buttons; every lift move
  ends in STALL ~0.8 s without the motor); 3. lift connected: home with Down, tests/lift_calibrate.py to set
  LIFT_TOP_COUNTS in BOTH bag_main files, watch how far it coasts past the bottom switch at 80%, then
  Up/Down/Stop/opposite in bag_main_bench.py; 4. bag_main.py on the ground (MAX_SPEED 50), open space, someone
  at the power switch.
- Confirm the tag keeps ranging on the power bank over long runs (some power banks shut off at low current).
- Lift UP direction is set (DIR 0 = UP) everywhere. Test the esp32.py typed-line forwarding with
  tests/loop_test.py if follow_me.py's lift keys are ever used again.
- New board: fix the Wi-Fi reset (still happens on the breakout's native USB; try a short/good cable, a powered
  hub, or a 470-1000 uF cap across the breakout's 5V/GND; check on the UBEC 5V rail) before
  lift_web.py; re-run tests/mcu_check.py to confirm "wifi scan: OK". Re-check every wiring pin on the new board
  (same pin map, untested on this board).
- Lift website: first hardware test of lift_web.py without the MD10C connected (STALL_CHECK = False, watch for
  LIFT: UP / STOP / timeout), then with the motor; UP_DIR already 0; add limit switches.
- bag_main.py (buttons, no website) is the program meant to become main.py once tested (ask before uploading).
  A website version would mean merging lift_web.py into it (asyncio). Not planned right now.
- Later: two anchors for steering; ultrasonic/ToF for obstacles and stairs.
