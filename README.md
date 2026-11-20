# Follow-me bag: ESP32 code

MicroPython code for the follow-me bag drivetrain (ESP32-S3, DFR0601, two FIT0186 motors),
the scissor lift (FIT0403 motor, Cytron MD10C) and the Qorvo DWM3001CDK UWB anchor. Forge (Northeastern) team project.

Current scope: front-wheel drive, straight-line following (distance only, no steering yet).
The drivetrain and UWB following work on the bench (wheels in the air); next step is the ground test.

> **Safety:** never run a motor program unless the wheels are off the ground, or the bag is in an
> open area with someone at the power switch. Every motor program turns the motors off in a
> `finally` block when stopped.

## Files

| File | What it does |
|---|---|
| `follow_me.py` | Main program: UWB distance sets the speed, encoders keep both wheels matched; lift on keys u / d / s, with the wheel/lift interlock |
| `follow_me_bench.py` | Same, with short distances for bench testing (stop 30 cm, start 40 cm, full speed 100 cm) |
| `lift_web.py` | Standalone lift test: the ESP32 makes its own Wi-Fi network and a phone web page with hold-to-run UP / DOWN / STOP (see "Lift website") |
| `tests/motor_check.py` | Runs each motor alone forward and reverse, then both; checks each encoder |
| `tests/motor_match.py` | Both motors at 80% with encoder speed matching, no UWB |
| `tests/uwb_distance.py` | Prints raw and smoothed UWB distance |
| `tests/uwb_test.py` | Prints everything the UWB sensor sends (raw) |
| `tests/uwb_send_commands.py` | Sends HELP, INITF, SAVE to the sensor over the header UART |
| `tests/uwb_baud_scan.py` | Checks the UART line and tries common baud rates |
| `tests/lift_test_encoder.py` | Runs the lift a short way in DIR 0 then DIR 1 and counts lift encoder A and B (wheels held off) |
| `tests/loop_test.py` | Harmless counter loop (no pins) for testing that stopping works |
| `tests/mcu_check.py` | New-board check, nothing wired: firmware, flash, PSRAM, pulse counter, RGB LED (GPIO 48), Wi-Fi scan |
| `tools/esp32.py` | Runs a file on the ESP32 so Ctrl+C really stops it and what you type reaches the program, plus `stop`, `mp` (mpremote with the fixes for this board) and `port`. Finds the board by itself (runs on your computer, not the board) |
| `.vscode/tasks.json` | VS Code tasks: Run, STOP, upload as main.py, REPL, list files, list devices (no port prompt) |
| `CLAUDE.md` | Full project notes (hardware, wiring, UWB setup, rules) |

## Pins

- Motor 1 (left): PWM GPIO 18, A GPIO 8, B GPIO 9, encoder A GPIO 40
- Motor 2 (right): PWM GPIO 10, A GPIO 11, B GPIO 12, encoder A GPIO 39
- Encoder A wires go through a 10k/20k divider with 1 nF to GND (the encoders output 5V).
- Lift (MD10C): PWM GPIO 14, DIR GPIO 13, MD10C GND -> ESP32 G
- Lift encoder: A (yellow) GPIO 42, B (white) GPIO 38, each through a 10k/20k divider (wired and tested)
- UWB sensor J10: pin 10 (sensor TX) -> GPIO 21, GPIO 47 -> pin 8 (sensor RX), pin 6 GND, pin 2 5V
- DFR0601 VCC -> ESP32 3V3.
- **The ESP32 G pin must be connected to the shared ground.** Missing ground caused most early bugs.

---

## Setup on a Mac

1. **Install the tools** (skip any you already have):
   - VS Code: https://code.visualstudio.com
   - Git and Python 3: open Terminal and run `xcode-select --install` (or `brew install git python`).
2. **Install mpremote** in Terminal:
   ```bash
   pip3 install --user mpremote
   ```
   If that refuses with "externally-managed-environment", use `brew install pipx` then `pipx install mpremote`.
   If `mpremote` is "command not found" afterwards, add its folder to your PATH (version number may differ):
   ```bash
   echo 'export PATH="$HOME/Library/Python/3.9/bin:$PATH"' >> ~/.zprofile
   ```
   then open a new Terminal window. `python3 -m mpremote` always works either way.
3. **Get the code.** In a terminal:
   ```bash
   cd ~/Documents
   git clone https://github.com/saicharanchallapalli10-crypto/follow-me-bag.git
   ```
   (Git asks you to sign in to GitHub the first time; the easiest way is `brew install gh` then `gh auth login`.)
4. **Open the folder in VS Code:** File > Open Folder > `follow-me-bag`.
5. **Plug in the ESP32 by its "COM" USB-C port** (not the one labelled "USB"; see "The ESP32 board" below)
   and check that it is found:
   ```bash
   python3 tools/esp32.py port
   ```
   It prints something like `/dev/cu.usbmodem595B0699471` (USB id `1a86:55d3`, shown by `mpremote devs`).
   No USB driver is needed on recent macOS.
6. **Test that run and stop work** with the harmless loop: open `tests/loop_test.py`, press **Cmd+Shift+B**,
   then press **Ctrl+C** in that terminal.
   You should see `STOPPED: program interrupted, board idle at the >>> prompt.`

From a normal Terminal (instead of VS Code):
```bash
python3 tools/esp32.py run tests/loop_test.py
```
```bash
python3 tools/esp32.py stop
```

## The ESP32 board (ESP32-S3-N8R2, two USB-C ports)

Since 2026-11-20 the board is an ESP32-S3-N8R2 DevKitC-style clone (8 MB flash, 2 MB PSRAM) with
MicroPython v1.29.0. It has two USB-C ports:

| Port | Chip | Mac name | Use it for |
|---|---|---|---|
| **COM** | WCH CH343 USB-serial (`1a86:55d3`) | `/dev/cu.usbmodem595B0699471` | **Everything**: run, stop, REPL, files |
| **USB** | ESP32-S3 native USB Serial/JTAG (`303a:1001`) | `/dev/cu.usbmodem101` | Flashing firmware only |

- **Always use the COM port.** With only the USB port plugged in, the board starts in download mode
  every time (even after RST), so MicroPython never runs and there is no REPL there.
- **Use `tools/esp32.py`, not plain mpremote, for running files.** On the COM port the Mac loses bytes
  when data is sent faster than the board's serial line takes it, so plain `mpremote run` of a bigger
  file fails with random `SyntaxError`s. `tools/esp32.py` sends data in 64-byte pieces at line speed.
  For other mpremote commands use `python3 tools/esp32.py mp ...`, for example:
  ```bash
  python3 tools/esp32.py mp ls
  ```
  ```bash
  python3 tools/esp32.py mp cp myfile.py :
  ```
  ```bash
  python3 tools/esp32.py mp exec "print(1+1)"
  ```
- **Reset lines:** the board resets when DTR and RTS differ. mpremote and `tools/esp32.py` keep both on,
  which never resets it. Thonny and `screen` may reset it when they connect; that is harmless.
- **Wi-Fi resets the board when it runs from the Mac's USB port** (`rst:0x1 (POWERON)` in the log as soon as
  Wi-Fi turns on). That is a power dip, not a code bug. If `tools/esp32.py run` sees the board reboot it
  prints a WARNING and exits. Try a short, good USB-C cable or a powered hub; on the bag the board gets 5 V from
  the UBEC instead.
- **RGB LED** is on GPIO 48 (`tests/mcu_check.py` showed green on 48, nothing on 38), so lift encoder B
  on GPIO 38 does not clash with it.
- **Flashing** (only if needed): move the cable to the USB port (the board is already in download mode
  there), use esptool on `/dev/cu.usbmodem101` with `--before no_reset --after no_reset`, then move the
  cable back to COM and press RST. Flashing through the COM port fails (the same lost-bytes problem).

## Setup on Windows

1. **Install the tools:**
   - VS Code: https://code.visualstudio.com
   - Python 3: https://www.python.org/downloads/ . In the installer, **tick "Add python.exe to PATH"**.
   - Git: https://git-scm.com/download/win (default options are fine).
2. **USB driver:** plug the board in by its **COM** port. It uses a WCH CH343 USB chip, which Windows 10/11
   normally drives with its built-in USB serial driver. If the board does not appear under Device Manager >
   Ports (COM & LPT), install WCH's CH343 driver (wch-ic.com, search "CH343SER"), then unplug and replug
   the board.
3. **Install mpremote** in PowerShell (or Command Prompt):
   ```powershell
   python -m pip install mpremote
   ```
   If `python` opens the Microsoft Store, Python was not added to PATH: rerun the installer, choose Modify,
   and tick "Add Python to environment variables". Use `python`, not `python3`, in all commands on Windows.
4. **Get the code.** In a terminal:
   ```powershell
   cd $HOME\Documents
   git clone https://github.com/saicharanchallapalli10-crypto/follow-me-bag.git
   ```
   Git for Windows opens a browser window to sign in to GitHub the first time.
5. **Open the folder in VS Code:** File > Open Folder > `follow-me-bag`.
6. **Find the ESP32's port:**
   ```powershell
   python -m mpremote devs
   ```
   The ESP32 is the COM port with `1a86:55d3` (WCH), for example `COM5`. `python tools\esp32.py port`
   should print the same port.
7. **Test that run and stop work** with the harmless loop: open `tests/loop_test.py`, press **Ctrl+Shift+B**,
   then press **Ctrl+C** in that terminal. You should see
   `STOPPED: program interrupted, board idle at the >>> prompt.`

   If the port is not found automatically, set it once (then open a new VS Code window):
   ```powershell
   setx ESP32_PORT COM5
   ```

From PowerShell (instead of VS Code):
```powershell
python tools\esp32.py run tests\loop_test.py
```
```powershell
python tools\esp32.py stop
```

> The Windows support in `tools/esp32.py` and `.vscode/tasks.json` has not been tested on a Windows
> machine yet. Test with `tests/loop_test.py` first. If STOP ever fails, use the bag's power switch.

---

## Everyday use (both)

Shortcuts: **Cmd** on Mac = **Ctrl** on Windows.

- **Run the open file:** Cmd+Shift+B (the port is found automatically; override with `ESP32_PORT`).
  Output appears in the terminal panel. The task runs `tools/esp32.py run`, a small wrapper around mpremote.
  Anything you type in that terminal and send with Enter goes to the program (used for the lift keys).
- **Stop it (motors off), two ways that both work:**
  1. Click in the Run terminal and press **Ctrl+C** (Ctrl+C on Mac too). The wrapper sends Ctrl-C to the ESP32
     and checks that it stopped.
  2. Run the task **ESP32: STOP program (motors off)** (Terminal > Run Task), or press the shortcut you set up
     below. It works from anywhere in VS Code, even if the Run terminal is closed or stuck.

  Both print `STOPPED: program interrupted, board idle at the >>> prompt.` when it worked, after the
  program's own output (for the motor programs, `Motors stopped` from their `finally` block).
  If you see `WARNING: could not confirm the stop`, use the power switch.
- **Why the wrapper:** plain `mpremote run` only quits on your computer when you press Ctrl+C. It never
  interrupts the board, so the program and the motors keep running. Do not run motor programs with plain
  `mpremote run`.
- **Close Thonny** (and any `screen`/PuTTY session on the ESP32) before using VS Code. Only one program can
  use a serial port at a time.
- **Make it start at power-up:** open `follow_me.py`, Terminal > Run Task > **Upload current file as main.py**.
  Lift the wheels first: the motors can start as soon as the ESP32 gets power.
- **Turn auto-start off:** Run Task > **Remove main.py**.
- **Interactive prompt:** Run Task > **Open REPL** (Ctrl-] to exit).

## Lift controls and the wheel/lift interlock

While `follow_me.py` (or `follow_me_bench.py`) runs, type in the Run terminal (or Thonny's shell) and press Enter:

| Key | What happens |
|---|---|
| `u` | Lift up for 1 s (`LIFT_RUN_MS`). Press `u` again while it moves to keep going, up to 4 s (`LIFT_MAX_MS`) |
| `d` | Lift down, same way |
| `s` | Stop the lift now |

**Interlock: the wheels and the lift are never powered at the same time.**
1. `u` / `d` first ramps the wheels down to 0, then waits until both wheel encoders read 0
   (at most 1.5 s, and the wheels are already unpowered by then).
2. Only then does the lift run. The wheels are held at 0 the whole time.
3. When the lift stops (time up, `s`, opposite key or a stall), everything waits 0.3 s, then following resumes.
4. Every motor write also checks the other motors' real PWM output. If the wheels and the lift would ever be
   on together, the program cuts **all** motors and stops with `INTERLOCK: ...`. That means a bug: tell
   whoever changed the code last.

The lift stops by itself if lift encoder A gets no pulses for 0.3 s at full lift power (stuck, at the end of
travel, or an encoder wiring problem). There are no limit switches, so keep the presses short and watch the lift.

**Before the first use:** run `tests/lift_test_encoder.py` with the lift at mid-height, see which DIR moves it
up, and set `LIFT_UP_DIR` near the top of `follow_me.py` (and `follow_me_bench.py`) to that value (0 or 1).
It is 0 until that is checked.

## Lift website (`lift_web.py`)

A standalone test that drives the scissor lift from a phone. The ESP32 creates its own Wi-Fi network
(**BagLift**, password **followme123**) and serves a page at **http://192.168.4.1** with three buttons:

- **UP / DOWN: hold to run.** While you hold a button the phone repeats the command every 150 ms.
  Let go and the lift stops. If no command arrives for 500 ms (`TIMEOUT_MS`), because the phone locked,
  Wi-Fi dropped or the page closed, the lift stops by itself.
- **STOP** stops it immediately.
- It starts gently (ramps up to 40%, `LIFT_SPEED`) and stops immediately. It only changes direction
  while the power is 0.
- It stops if lift encoder A gets no pulses at full power (stuck or at the end of travel, `STALL_CHECK`),
  or when a limit switch is pressed. After one of those stops, let go of the button before it will move again.
- The wheel motors are held off the whole time. Ctrl+C / STOP turns the lift off and switches the Wi-Fi off.

It has not been run on the hardware yet. Do the first test below before connecting the motor.

**Wiring** (same as `follow_me.py`):
- GPIO 14 -> MD10C PWM, GPIO 13 -> MD10C DIR, **MD10C GND -> ESP32 G** (shared ground)
- MD10C power from the 12V bus, lift motor on the MD10C motor terminals
- Lift encoder A (yellow) -> GPIO 42 through its 10k/20k divider (used for the stall check)

**Run it from VS Code:** open `lift_web.py`, press **Cmd+Shift+B**.
(On the new board, Wi-Fi reset the ESP32 when powered from the Mac's USB port; see "The ESP32 board".)
The terminal shows:
```
Lift website ready. Join Wi-Fi BagLift (password followme123), open http://192.168.4.1
```
Stop it with **Ctrl+C** in that terminal or the **STOP** task, the same as the other programs. Typing in the
terminal does nothing in this program; use the web page.

**Connect a phone:**
1. Settings > Wi-Fi > join **BagLift**, password `followme123`.
2. The phone will say **"No internet connection"**. That is expected: the ESP32 is not connected to the
   internet. Choose **stay connected / use this network anyway** (Android: "Keep Wi-Fi connection" or
   "Use network as is"; iPhone: just stay on it).
3. Open the browser and type **http://192.168.4.1** (type the `http://`).
4. The page shows `Stopped` at the top. If it says `No reply from the bag`, check the phone is still on
   BagLift. If the page will not load at all, turn off mobile data for the test (some phones send everything
   over mobile data when the Wi-Fi has no internet).

**First test, without the MD10C connected** (nothing can move):
1. Unplug the MD10C's PWM and DIR wires from the ESP32 (or leave the MD10C unpowered).
2. In `lift_web.py` set `STALL_CHECK = False` (with no motor there are no encoder pulses, so the stall
   check would stop it after about 0.7 s).
3. Run it, connect the phone, and watch the terminal:
   - Hold **UP**: `LIFT: UP`, then about once a second `LIFT UP  power: 40 % ...`
   - Let go: `LIFT: STOP (button released)`
   - Hold **DOWN**: `LIFT: DOWN`. Let go: `LIFT: STOP (button released)`
   - Timeout: a single command with no repeats must stop by itself. Join **BagLift** on the Mac too
     (the USB cable stays connected), then in a normal Terminal run:
     ```bash
     curl "http://192.168.4.1/cmd?d=up"
     ```
     The terminal shows `LIFT: UP`, then half a second later `LIFT: STOP (timeout: no command for 500 ms)`.
     (Locking the phone or leaving the page while holding also stops it, but as `button released`, because
     the page sends a stop when it is hidden.)
4. Set `STALL_CHECK = True` again before connecting the motor.

Then connect the MD10C, put the lift at mid-height, and use short presses first.

**Flip the direction (`UP_DIR`):** if holding UP moves the lift down, change `UP_DIR` at the top of
`lift_web.py` from 0 to 1 (or 1 to 0). Use the same value for `LIFT_UP_DIR` in `follow_me.py` and
`follow_me_bench.py`. Set this before adding limit switches, because the top switch only blocks the
direction the program thinks is UP.

**Add limit switches (optional):**
1. Use free GPIOs, for example **GPIO 6** (top) and **GPIO 7** (bottom). Avoid pins already used
   (8-14, 18, 21, 38-42, 47) and GPIO 0, 3, 45, 46 (boot pins).
2. Wire each switch between its GPIO and **GND** (no resistor needed; the program turns on the internal pull-up).
   Use the switch's **NC** (normally closed) contact: a broken wire then looks like a pressed switch, so
   the lift stops instead of running past the end.
3. In `lift_web.py` set `TOP_LIMIT_PIN = 6` and `BOTTOM_LIMIT_PIN = 7`. Keep `LIMIT_PRESSED = 1` for NC
   switches (use 0 for NO switches).
4. Run it and check the page: it shows `| top switch pressed` while you press the switch by hand. With
   the top switch pressed, UP must refuse (`LIFT: STOP (top limit switch)`) and DOWN must still work.
   If a pin is set but its switch is not connected, that direction will not move at all (fail-safe).

## One program at a time (lift website vs. follow-me)

The ESP32 runs **one program at a time**. `follow_me.py` (following, lift on terminal keys) and
`lift_web.py` (lift from the phone) are separate tests for now: running one stops the other, and the
website does not exist while `follow_me.py` runs.

The plan is to merge them into **one asyncio program** with three parts running together: the
follow-me loop, the web server and the lift loop, with the wheel/lift interlock from `follow_me.py`.
That merged program then becomes `main.py`, so it starts at power-up. It has not been written yet.

## Keyboard shortcut for STOP (one time, per computer)

VS Code keyboard shortcuts are saved in your user settings, not in this folder, so each person adds them once.

1. Cmd+Shift+P (Windows: Ctrl+Shift+P), type **Preferences: Open Keyboard Shortcuts (JSON)**, press Enter.
2. Paste this entry inside the `[ ]` (add a comma after the previous entry if there is one), then save:

   ```json
   {
     "key": "ctrl+alt+s",
     "command": "workbench.action.tasks.runTask",
     "args": "ESP32: STOP program (motors off)"
   }
   ```

3. So the shortcut also works while the cursor is in a terminal: Cmd+Shift+P,
   **Preferences: Open User Settings (JSON)**, and add this line inside the outer `{ }`:

   ```json
   "terminal.integrated.commandsToSkipShell": ["workbench.action.tasks.runTask"],
   ```

Now **Ctrl+Option+S** (Mac) / **Ctrl+Alt+S** (Windows) stops the program from anywhere in VS Code.
Test it once with `tests/loop_test.py`.

## UWB boards

The UWB boards are already configured and save their settings (see `CLAUDE.md`). The bag board streams
distances to the ESP32 at 115200 baud as soon as it has power. The tag is powered from a USB power bank
through its **J9** port.

To open a UWB board's console (rarely needed):
- Mac: `screen /dev/cu.usbmodem… 115200`, exit with Ctrl-A, K, Y.
- Windows: PuTTY (https://www.putty.org), Connection type **Serial**, the board's COM port, speed 115200.

## Standalone power

When running without a laptop, the ESP32 is powered from the UBEC through the 5V jumper.
Unplug that jumper whenever USB is connected.
