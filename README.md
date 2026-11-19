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
| `tests/motor_check.py` | Runs each motor alone forward and reverse, then both; checks each encoder |
| `tests/motor_match.py` | Both motors at 80% with encoder speed matching, no UWB |
| `tests/uwb_distance.py` | Prints raw and smoothed UWB distance |
| `tests/uwb_test.py` | Prints everything the UWB sensor sends (raw) |
| `tests/uwb_send_commands.py` | Sends HELP, INITF, SAVE to the sensor over the header UART |
| `tests/uwb_baud_scan.py` | Checks the UART line and tries common baud rates |
| `tests/lift_test_encoder.py` | Runs the lift a short way in DIR 0 then DIR 1 and counts lift encoder A and B (wheels held off) |
| `tests/loop_test.py` | Harmless counter loop (no pins) for testing that stopping works |
| `tools/esp32.py` | Runs a file on the ESP32 so Ctrl+C really stops it and what you type reaches the program, plus a `stop` command (runs on your computer, not the board) |
| `.vscode/tasks.json` | VS Code tasks: Run, STOP, upload as main.py, REPL, list files, list devices |
| `CLAUDE.md` | Full project notes (hardware, wiring, UWB setup, rules) |

## Pins

- Motor 1 (left): PWM GPIO 18, A GPIO 8, B GPIO 9, encoder A GPIO 40
- Motor 2 (right): PWM GPIO 10, A GPIO 11, B GPIO 12, encoder A GPIO 39
- Encoder A wires go through a 10k/20k divider with 1 nF to GND (the encoders output 5V).
- Lift (MD10C): PWM GPIO 14, DIR GPIO 13, MD10C GND -> ESP32 G
- Lift encoder: A (yellow) GPIO 42, B (white) GPIO 38, both through a divider
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
5. **Plug in the ESP32** (USB-C port labelled UART / the CP2102N one) and find its port:
   ```bash
   mpremote devs
   ```
   The ESP32 is the `/dev/cu.usbserial-…` line (for example `/dev/cu.usbserial-130`; the number depends on
   which USB port you use). UWB boards show up as `/dev/cu.usbmodem…`.
   No USB driver is needed on recent macOS.
6. **Test that run and stop work** with the harmless loop: open `tests/loop_test.py`, press **Cmd+Shift+B**,
   press Enter at the port prompt (or type your port), then press **Ctrl+C** in that terminal.
   You should see `STOPPED: program interrupted, board idle at the >>> prompt.`

From a normal Terminal (instead of VS Code):
```bash
python3 tools/esp32.py run tests/loop_test.py --port /dev/cu.usbserial-130
```
```bash
python3 tools/esp32.py stop
```

## Setup on Windows

1. **Install the tools:**
   - VS Code: https://code.visualstudio.com
   - Python 3: https://www.python.org/downloads/ . In the installer, **tick "Add python.exe to PATH"**.
   - Git: https://git-scm.com/download/win (default options are fine).
2. **USB driver:** the ESP32 DevKit uses a Silicon Labs CP2102N USB chip. Windows 10/11 usually installs the
   driver by itself. If the board does not appear under Device Manager > Ports (COM & LPT), install the
   "CP210x Universal Windows Driver" from
   https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers , then unplug and replug the board.
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
   The ESP32 is the COM port with `10c4:ea60` (Silicon Labs), for example `COM5`. You can also check Device
   Manager > Ports (COM & LPT): "Silicon Labs CP210x USB to UART Bridge (COM5)".
7. **Test that run and stop work** with the harmless loop: open `tests/loop_test.py`, press **Ctrl+Shift+B**.
   The port prompt shows the Mac default; **replace it with your COM port** (for example `COM5`) and press Enter.
   Then press **Ctrl+C** in that terminal. You should see
   `STOPPED: program interrupted, board idle at the >>> prompt.`

   To skip typing the port in the STOP task and the terminal, set it once (then open a new VS Code window):
   ```powershell
   setx ESP32_PORT COM5
   ```

From PowerShell (instead of VS Code):
```powershell
python tools\esp32.py run tests\loop_test.py --port COM5
```
```powershell
python tools\esp32.py stop
```

> The Windows support in `tools/esp32.py` and `.vscode/tasks.json` has not been tested on a Windows
> machine yet. Test with `tests/loop_test.py` first. If STOP ever fails, use the bag's power switch.

---

## Everyday use (both)

Shortcuts: **Cmd** on Mac = **Ctrl** on Windows.

- **Run the open file:** Cmd+Shift+B, enter the port at the prompt.
  Output appears in the terminal panel. The task runs `tools/esp32.py run`, a small wrapper around mpremote.
  Anything you type in that terminal and send with Enter goes to the program (used for the lift keys).
- **Stop it (motors off), two ways that both work:**
  1. Click in the Run terminal and press **Ctrl+C** (Ctrl+C on Mac too). The wrapper sends Ctrl-C to the ESP32
     and checks that it stopped.
  2. Run the task **ESP32: STOP program (motors off)** (Terminal > Run Task), or press the shortcut you set up
     below. It works from anywhere in VS Code, even if the Run terminal is closed or stuck, and does not ask
     for a port.

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
