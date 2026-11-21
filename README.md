# Follow-me bag: ESP32 code

MicroPython code for an autonomous bag that follows a person (Forge, Northeastern team project).
An ESP32-S3 drives two wheel motors (DFRobot DFR0601 driver, FIT0186 motors), a scissor lift
(FIT0403 motor, Cytron MD10C driver) and reads the distance to the person from a Qorvo DWM3001CDK UWB pair.

Current scope: straight-line following (distance only, no steering yet) plus lift buttons.

> **Safety first.** Never run a motor program unless the wheels are off the ground, or the bag is in an
> open area with someone at the power switch. Every motor program turns all motors off when it stops.
> If anything looks wrong, **flip the power switch**: that always works.

---

## Contents

1. [Quick start (Mac and Windows)](#1-quick-start-mac-and-windows)
2. [Run it with Claude Code](#2-run-it-with-claude-code)
3. [Command cheat sheet](#3-command-cheat-sheet)
4. [The bag program (`bag_main.py`)](#4-the-bag-program-bag_mainpy)
5. [Wiring](#5-wiring)
6. [Test steps, in order](#6-test-steps-in-order)
7. [All files](#7-all-files)
8. [Running from VS Code](#8-running-from-vs-code)
9. [Board, UWB and power notes](#9-board-uwb-and-power-notes)
10. [Lift website (`lift_web.py`, separate test)](#10-lift-website-lift_webpy-separate-test)

---

## 1. Quick start (Mac and Windows)

Do this once per computer. Every step has a Mac line and a Windows line; do only yours.

### Step 1: install Python and Git

| | Mac | Windows |
|---|---|---|
| Python 3 | Open **Terminal**, run `xcode-select --install` (or `brew install python`) | Download from https://www.python.org/downloads/ and **tick "Add python.exe to PATH"** in the installer |
| Git | comes with the line above | Download from https://git-scm.com/download/win (default options) |

### Step 2: install mpremote (talks to the ESP32)

Mac (Terminal):
```bash
pip3 install --user mpremote
```
Windows (PowerShell):
```powershell
python -m pip install mpremote
```

> Mac: if it says "externally-managed-environment", run `brew install pipx` then `pipx install mpremote`.
> Windows: if `python` opens the Microsoft Store, rerun the Python installer, choose **Modify**, and tick
> "Add Python to environment variables".

### Step 3: download this code

Mac:
```bash
cd ~/Documents && git clone https://github.com/saicharanchallapalli10-crypto/follow-me-bag.git
```
Windows (PowerShell):
```powershell
cd $HOME\Documents; git clone https://github.com/saicharanchallapalli10-crypto/follow-me-bag.git
```

### Step 4: plug in the ESP32 and check it is found

Plug a USB-C cable from the computer into the ESP32 board, then go into the folder and ask for the port:

Mac:
```bash
cd ~/Documents/follow-me-bag && python3 tools/esp32.py port
```
Windows:
```powershell
cd $HOME\Documents\follow-me-bag; python tools/esp32.py port
```

It prints the board's port: `/dev/cu.usbmodem...` on a Mac, `COM3` (or another number) on Windows.
If it says it can't find the board, try the board's other USB-C port, another cable, and close Thonny
(only one program can use the port).

### Step 5: check that run and stop work (harmless, no motors)

Mac:
```bash
python3 tools/esp32.py run tests/loop_test.py
```
Windows:
```powershell
python tools/esp32.py run tests/loop_test.py
```

It counts up. Press **Ctrl+C** (Ctrl on the Mac too). You should see
`STOPPED: program interrupted, board idle at the >>> prompt.` You're set up.

> **The only difference between Mac and Windows commands:** Mac uses `python3`, Windows uses `python`.
> Everything after that is the same (forward slashes `/` work on Windows too).
> The Windows side of `tools/esp32.py` has not been tested on a Windows PC yet: try `tests/loop_test.py`
> first, and if stopping ever fails, use the power switch.

---

## 2. Run it with Claude Code

Claude Code is an AI assistant that can read this project, run the test programs on the ESP32 for you,
read their output and fix the code. This repo includes `CLAUDE.md`, which Claude reads automatically: it
holds the wiring, the test history and the safety rules, so Claude already knows the hardware.

### Install it (pick one)

- **Desktop app (easiest, Mac and Windows):** download the Claude app from https://claude.ai/download,
  sign in, open the **Code** tab, and choose the `follow-me-bag` folder.
- **Terminal version:**

  Mac:
  ```bash
  curl -fsSL https://claude.ai/install.sh | bash
  ```
  Windows (PowerShell):
  ```powershell
  irm https://claude.ai/install.ps1 | iex
  ```
  Then start it inside the project folder:
  ```bash
  cd ~/Documents/follow-me-bag
  claude
  ```
  (Windows: `cd $HOME\Documents\follow-me-bag` then `claude`.)

Do steps 1 to 4 of the Quick start first: Claude uses the same Python, mpremote and `tools/esp32.py`.

### Just ask in plain English

| You type | What Claude does |
|---|---|
| `Run the button check` | Runs `tests/button_check.py` and tells you which button is on which pin |
| `Run the bench test, the wheels are off the ground` | Runs `bag_main_bench.py`, reads the output |
| `Stop the program` | Runs `tools/esp32.py stop` (all motors off) |
| `The lift went down when I pressed Up, here's the output: ...` | Finds the cause, fixes the code |
| `Help me calibrate the lift top` | Walks you through `tests/lift_calibrate.py` |
| `What does the status line mean?` | Explains it from the code |

Claude asks before anything risky: it will want you to confirm the wheels are off the ground before any
motor program, and it never uploads a program as `main.py` (auto-start at power-up) unless you ask.

### Running a command yourself inside Claude Code

- **Desktop app:** commands Claude gives you have a **Run** button. Click it.
- **Terminal version:** type `!` and the command, for example
  ```
  ! python3 tools/esp32.py run tests/button_check.py
  ```
  (Windows: `! python tools/esp32.py run tests/button_check.py`). Claude sees the output, so you can
  just say "what happened?" afterwards.

**Programs that end by themselves** (the button checks, `tests/lift_80.py`, `tests/loop_test.py`) are fine to
run this way. **Programs that run until you stop them** (`bag_main.py`, `bag_main_bench.py`,
`tests/lift_buttons.py`, `tests/lift_calibrate.py`) are best run in a normal terminal or VS Code
(section 8), where **Ctrl+C** stops them. From anywhere, this also stops them, motors off:

Mac:
```bash
python3 tools/esp32.py stop
```
Windows:
```powershell
python tools/esp32.py stop
```

---

## 3. Command cheat sheet

Run these from inside the `follow-me-bag` folder. **Windows: write `python` instead of `python3`.**

| What | Command | Ends by itself? |
|---|---|---|
| Find the board | `python3 tools/esp32.py port` | yes |
| **Stop anything (motors off)** | `python3 tools/esp32.py stop` | yes |
| Check all buttons + bottom switch (no motors) | `python3 tools/esp32.py run tests/button_check.py` | no: Ctrl+C |
| Check one button (20 s) | `python3 tools/esp32.py run tests/button4.py` (also `button17.py`, `button6.py`) | yes |
| Find which pin a button is on (30 s) | `python3 tools/esp32.py run tests/pin_finder.py` | yes |
| Lift on the buttons only (wheels off) | `python3 tools/esp32.py run tests/lift_buttons.py` | no: Ctrl+C |
| Find the lift's top (`LIFT_TOP_COUNTS`) | `python3 tools/esp32.py run tests/lift_calibrate.py` | no: Ctrl+C |
| **Bag program, bench** (30 / 40 / 100 cm) | `python3 tools/esp32.py run bag_main_bench.py` | no: Ctrl+C |
| **Bag program, real** (100 / 115 / 300 cm) | `python3 tools/esp32.py run bag_main.py` | no: Ctrl+C |
| UWB distance only | `python3 tools/esp32.py run tests/uwb_distance.py` | no: Ctrl+C |

Never run motor programs with plain `mpremote run`: when you press Ctrl+C it quits on the computer but the
program and the motors keep running on the ESP32. `tools/esp32.py` really stops them.

---

## 4. The bag program (`bag_main.py`)

One program does everything: follow the person and work the lift from three buttons. There are two copies
that are identical except for the first line:

| File | First line | Distances (stop / start / full speed) | Top speed |
|---|---|---|---|
| `bag_main_bench.py` | `BENCH = True` | 30 / 40 / 100 cm | 80% |
| `bag_main.py` | `BENCH = False` | 100 / 115 / 300 cm | 50% (first ground tests) |

### At start-up

It prints a **pin map** with the live state of every button and the bottom switch. Check it against the
wiring each time. Then:

- `NOT ARMED`: the wheels will not move yet.
- `NOT HOMED` (or `HOMED at start` if the lift is resting on the bottom switch).

### Following

1. **Arm it:** stand next to the bag (within the stop distance) for 1 second. It prints `ARMED`.
2. **Walk away:** past the start distance it drives, faster the farther you are (up to the top speed),
   with gentle ramps. The two wheels are kept at the same speed with their encoders.
3. **Come back:** at the stop distance it stops.
4. **No tag reading for 1 s:** it stops. **No tag for 3 s:** `DISARMED`. Arm it again the same way.

### Lift buttons

| Button | What happens |
|---|---|
| **Up** (GPIO 4) | lift goes up and keeps going until something stops it |
| **Down** (GPIO 17) | lift goes down and keeps going until something stops it |
| **Stop** (GPIO 6) | stops the lift |

- Pressing the **opposite** button while it moves only **stops** it (press again to go the other way).
- **Going down** it stops at the **bottom switch**. That is "homing": the lift position is reset to 0.
- **Going up** it stops at the **soft top**: `LIFT_TOP_COUNTS` encoder pulses above the bottom switch.
- It also stops on a **stall** (motor powered but no encoder pulses for 0.3 s) and after **8 s** in one move.
- **Until it has been homed once** after power-up, it doesn't know its height, so each Up move is limited to
  1.5 s and it prints `NOT HOMED: press Down to home`.
- It refuses: Down while on the bottom switch, Up at the soft top, anything while Stop is held.
- Every stop prints the reason and the position, for example `LIFT: STOP UP (soft top 3000) ... position 3006`.
- A button held down at power-up is ignored until you let go.

### Wheels and lift never together

The lift only starts while the wheels are stopped (stand next to the bag). If the wheels start moving
(you walked away), the lift stops first. Every motor command also checks the other motors' real output; if
both would ever be on, **all** motors are cut and the program ends with `INTERLOCK: ...` (that means a bug).

### The status line (every 0.3 s)

```
FOLLOW    ARMED | dist 85 tgt 67 base 65.0 | M1 214 M2 219 p1 66.2 | lift OFF  pos 0 homed
```
mode (NOT-ARMED / NO-TAG / STOPPED / FOLLOW), armed, distance (cm), target and actual power (%),
wheel encoder counts per 0.1 s, wheel 1 power, lift (OFF / UP / DOWN), lift position, homed or not.
Every 5 s it also prints the worst loop time.

### Settings worth knowing (top of the file)

`MAX_SPEED` (never above 80), `LIFT_SPEED` (80), `LIFT_TOP_COUNTS` (**placeholder 3000, calibrate it**),
`UP_DIR` (0 = up, checked), `LIMIT_PRESSED` (0 for the switch's NO contact, 1 if you rewire to NC),
`LIFT_WHILE_DRIVING` (False). If you change a setting, change it in **both** `bag_main.py` and
`bag_main_bench.py` (only the first line may differ).

---

## 5. Wiring

### Buttons and the bottom switch (internal pull-ups: no resistors)

| Part | ESP32 GPIO | Breakout terminal | Other leg |
|---|---|---|---|
| Up button (4 legs) | 4 | **4** | one diagonal leg to terminal 4, the opposite diagonal leg to **GND** |
| Down button (4 legs) | 17 | **17** | one diagonal leg to terminal 17, the opposite diagonal leg to **GND** |
| Stop button (4 legs) | 6 | **6** | one diagonal leg to terminal 6, the opposite diagonal leg to **GND** |
| Bottom limit switch | 7 | **7** | **COM to GND, NO to terminal 7**, NC unused |

- Use **diagonal** legs on the 4-leg buttons: they are always on opposite sides of the switch.
- Never connect a button to 3V3 or 5V. Released reads 1, pressed reads 0.
- The bottom switch is mounted at the **lowest height the lift may reach**. There is no top switch.

### Everything else (confirmed on the hardware)

| Function | ESP32 pin | Goes to |
|---|---|---|
| Wheel 1 PWM / A / B | 18 / 8 / 9 | DFR0601 P1 / A1 / B1 |
| Wheel 2 PWM / A / B | 10 / 11 / 12 | DFR0601 P2 / A2 / B2 |
| Wheel 1 encoder A | 40 | yellow wire via 10k/20k divider + 1 nF to GND |
| Wheel 2 encoder A | 39 | yellow wire via 10k/20k divider + 1 nF to GND |
| Lift PWM / DIR | 14 / 13 | MD10C PWM / DIR (DIR 0 = up) |
| Lift encoder A / B | 42 / 38 | yellow / white, each via 10k/20k divider |
| UWB: sensor TX to ESP32 RX | 21 | DWM3001CDK J10 pin 10 |
| UWB: ESP32 TX to sensor RX | 47 | DWM3001CDK J10 pin 8 |

- DFR0601 VCC to ESP32 3V3; MD10C GND to ESP32 G; UWB J10 pin 2 to 5V, pin 6 to GND.
- **The ESP32 G pin must be on the shared ground.** A missing ground caused most early bugs.
- Power: 12V LiFePO4, 15A fuse, switch, 12V bus (DFR0601, MD10C, UBEC). The UBEC makes 5V for the breadboard.

---

## 6. Test steps, in order

Do them one at a time; send the output (or tell Claude) after each.

1. **Buttons** (no motors): `tests/button_check.py`. Press each button and the bottom switch; each press
   must show once, on the right GPIO. Done: Up 4, Down 17, Stop 6 checked.
2. **Bench program, lift motor unplugged, wheels in the air:** `bag_main_bench.py`. Check arming, following,
   the lost-tag stop, and the buttons (watch the prints and the MD10C LED). With the motor unplugged every
   lift move ends in `STALL` after about 0.8 s; that is expected (or set `STALL_CHECK = False` for this test).
3. **Lift connected**, lift a bit above its lowest point:
   - `tests/lift_calibrate.py`: press **Down** until it stops at the bottom switch (`HOMED`), then **Up** in
     short presses (Up, then Stop) to the highest **safe** height. Note the position, put it (minus a small
     margin) in `LIFT_TOP_COUNTS` in both bag_main files.
   - Then `bag_main_bench.py`: Up / Down / Stop and the opposite button.
4. **On the ground, later:** `bag_main.py` (real distances, top speed 50%) in an open space, with someone at
   the power switch.

---

## 7. All files

| File | What it does |
|---|---|
| `bag_main.py` | **The bag program**, real distances (see section 4) |
| `bag_main_bench.py` | Same, bench distances (`BENCH = True`) |
| `tests/lift_calibrate.py` | Homes the lift, then prints the position as you move it up: find `LIFT_TOP_COUNTS` |
| `tests/lift_buttons.py` | Lift on the Up/Down/Stop buttons only, no homing (wheels held off) |
| `tests/lift_cw.py` / `tests/lift_ccw.py` | Lift up (DIR 0) / down (DIR 1) at 80% until Stop, a stall, the bottom switch or 30 s |
| `tests/lift_80.py` | Lift at 80% for about 2 s in one direction |
| `tests/lift_direction.py` | Proves DIR reverses the lift (quadrature count) |
| `tests/lift_test_encoder.py` | Lift a short way each direction, counts encoder A and B |
| `tests/button_check.py` | Prints every press of Up/Down/Stop/bottom switch (no motors) |
| `tests/button4.py`, `button6.py`, `button17.py`, `button5.py` | One GPIO for 20 s, then ends |
| `tests/pin_finder.py` | Watches all free GPIOs for 30 s: shows which pin a button is really on |
| `tests/limit_switch.py` | Limit switch on GPIO 7, prints PRESSED / RELEASED |
| `follow_me.py` / `follow_me_bench.py` | Older follow-me program with lift on typed keys u / d / s |
| `lift_web.py` | Lift from a phone over the ESP32's own Wi-Fi (section 10) |
| `tests/motor_check.py`, `motor_match.py`, `test_one_motor.py`, `test_each_channel.py` | Wheel motor and encoder tests |
| `tests/uwb_distance.py`, `uwb_test.py`, `uwb_send_commands.py`, `uwb_baud_scan.py` | UWB tests |
| `tests/loop_test.py` | Harmless counter: test that stopping works |
| `tests/mcu_check.py` | New-board check, nothing wired |
| `tools/esp32.py` | Runs a file on the ESP32 so Ctrl+C really stops it; also `stop`, `port`, `mp` (mpremote) |
| `.vscode/tasks.json` | VS Code tasks: Run, STOP, upload as main.py, REPL, list files/devices |
| `CLAUDE.md` | Full project notes for people and for Claude Code |

---

## 8. Running from VS Code

Install VS Code from https://code.visualstudio.com, then **File > Open Folder > follow-me-bag**.

- **Run the open file:** **Cmd+Shift+B** (Mac) / **Ctrl+Shift+B** (Windows). Output shows in the terminal panel.
- **Stop it:** click in that terminal and press **Ctrl+C**, or Terminal > Run Task >
  **ESP32: STOP program (motors off)** (works even if the terminal is stuck).
- **Auto-start at power-up:** Run Task > **Upload current file as main.py**. Lift the wheels first: the motors
  can start as soon as the ESP32 gets power. Undo with **Remove main.py**.
- **REPL:** Run Task > **Open REPL** (Ctrl-] to exit).
- Close Thonny first: only one program can use the board's port.

**Optional STOP shortcut** (once per computer): Cmd/Ctrl+Shift+P, **Preferences: Open Keyboard Shortcuts
(JSON)**, paste inside the `[ ]`:
```json
{ "key": "ctrl+alt+s", "command": "workbench.action.tasks.runTask", "args": "ESP32: STOP program (motors off)" }
```
and in **Preferences: Open User Settings (JSON)** add
`"terminal.integrated.commandsToSkipShell": ["workbench.action.tasks.runTask"],`.
Now Ctrl+Option+S (Mac) / Ctrl+Alt+S (Windows) stops the program from anywhere in VS Code.

If the port isn't found automatically, set it: Mac `export ESP32_PORT=/dev/cu.usbmodem101`,
Windows `setx ESP32_PORT COM5` (then open a new window).

---

## 9. Board, UWB and power notes

- **Board:** ESP32-S3-N8R2 (8 MB flash, 2 MB PSRAM), MicroPython v1.29.0, in a Freenove breakout with screw
  terminals. It has two USB-C ports. In the breakout, the port marked **USB** runs MicroPython directly and
  is the one `tools/esp32.py` prefers. The **COM** port (WCH CH343 chip) also works; on the Mac it loses data
  if sent too fast, which `tools/esp32.py` handles by pacing. Windows: if the COM port doesn't show in
  Device Manager > Ports, install WCH's CH343 driver (wch-ic.com, "CH343SER").
- **Wi-Fi resets the board** on USB power right now (power dip, cause still being found). It only matters for
  `lift_web.py`; the bag program doesn't use Wi-Fi.
- **UWB:** both boards are configured and remember it (details in `CLAUDE.md`). The bag board streams
  distances at 115200 baud as soon as it has power. The tag runs from a USB power bank through its **J9** port.
  To open a UWB board's console (rarely needed): Mac `screen /dev/cu.usbmodem... 115200` (exit Ctrl-A, K, Y);
  Windows PuTTY, Serial, the board's COM port, 115200.
- **Standalone power:** without a laptop the ESP32 gets 5V from the UBEC through the 5V jumper. Unplug that
  jumper whenever USB is connected.

---

## 10. Lift website (`lift_web.py`, separate test)

A standalone test that drives the lift from a phone. The ESP32 makes its own Wi-Fi network **BagLift**
(password **followme123**) with a page at **http://192.168.4.1**: hold UP / DOWN to run, let go to stop,
STOP button. If no command arrives for 0.5 s (phone locked, Wi-Fi dropped) it stops. Wheels held off.

It has **not** run on the hardware yet, and Wi-Fi currently resets the board on USB power (section 9).
The phone will say "No internet connection": stay connected, then type `http://192.168.4.1`.
First test without the motor: set `STALL_CHECK = False`, check the terminal shows `LIFT: UP` / `LIFT: STOP`,
then set it back to True. `UP_DIR` is already set to 0 (checked).

The ESP32 runs one program at a time, so the website and the bag program can't run together yet.
The plan is to merge them into one program that becomes `main.py`.
