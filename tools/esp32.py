#!/usr/bin/env python3
"""Run and stop MicroPython programs on the ESP32 (macOS, mpremote).

    python3 tools/esp32.py run <file.py> [--port PORT]
    python3 tools/esp32.py stop [--port PORT]
    python3 tools/esp32.py mp <mpremote args>      e.g.  mp ls   mp cp a.py :   mp exec "print(1)"   mp repl
    python3 tools/esp32.py port                    prints the port it would use

Why this exists: when `mpremote run` gets Ctrl+C it only exits on the Mac. It never sends
Ctrl-C to the board, so the program (and the motors) keep running on the ESP32.

Board (since 2026-11-20): ESP32-S3-N8R2 DevKitC clone, cable in the "COM" USB-C port (WCH CH343,
USB id 1a86:55d3, macOS name /dev/cu.usbmodem<serial>). Two quirks this file handles:
- Pacing: the CH343 + macOS driver loses data when a new write arrives while earlier bytes are still
  being sent (plain `mpremote run` of a 3 KB file failed 10/10). Every write is cut into 64-byte pieces
  and the next piece waits until the previous one has gone out at 115200 baud. `mp` gives mpremote
  the same pacing. Plain `mpremote` is fine for small things (ls, short exec) but not for `run`.
- DTR/RTS: the board resets when DTR and RTS differ (classic auto-reset circuit). DTR=RTS=1 (pyserial's
  default on open, and what this file sets) never resets it; mpremote's close order is also safe.
The "USB" port (native USB Serial/JTAG, 303a:1001) is for flashing only: on that port alone the board
always starts in download mode, so there is no REPL there.

run:  sends FILE to the board the same way `mpremote run` does (mpremote's own serial code),
      shows its output, and sends each line you type (+ Enter) to the program's input
      (follow_me.py uses this for the lift keys u / d / s). Ctrl+C in the terminal, or VS Code
      closing the task, then sends the stop sequence below.
stop: ends any mpremote/run process using the ESP32, opens the port, sends ONE Ctrl-C
      (KeyboardInterrupt -> the program's finally block turns the motors off), waits for
      the REPL prompt, and checks the board has gone quiet.

Port: --port, else $ESP32_PORT, else auto-detect by USB id: the only WCH CH343/CH9102 port
(1a86:55d3 / 55d4), else the only CP210x port (old board). UWB boards (Qorvo/SEGGER) are never
picked. If only the ESP32's native "USB" port is found, it says to move the cable to "COM".
Pacing is on for WCH ports; force it with ESP32_PACE=1 or turn it off with ESP32_PACE=0.

Windows (use `python` instead of `python3`): same auto-detect (COM ports via pyserial).
Windows paths are untested.
"""
import os
import queue
import signal
import subprocess
import sys
import threading
import time

WINDOWS = os.name == "nt"
BAUD = 115200

VID_WCH = 0x1A86          # CH343 / CH9102: the "COM" port of the current ESP32-S3 board
PIDS_WCH = (0x55D3, 0x55D4)
VID_CP210X = 0x10C4       # CP2102N: the old DevKit
VID_ESPRESSIF = 0x303A    # 0x1001 = native USB Serial/JTAG ("USB" port, flashing only)


def say(*args):
    # The terminal may already be gone (VS Code closed the task); never crash on print.
    try:
        print("[esp32]", *args, flush=True)
    except (OSError, ValueError):
        pass


def list_usb_ports():
    from serial.tools import list_ports  # pyserial, installed with mpremote

    ports = list_ports.comports()
    if not WINDOWS:
        # macOS lists both /dev/tty.* and /dev/cu.*; use the cu.* ones.
        ports = [p for p in ports if p.device.startswith("/dev/cu.")]
    return ports


def port_vid(port):
    for p in list_usb_ports():
        if p.device == port:
            return p.vid
    return None


def pick_port(arg_port):
    port = arg_port or os.environ.get("ESP32_PORT")
    if port:
        return port
    ports = list_usb_ports()
    # MicroPython's own native-USB serial (303a:4001): the "USB" port when the board runs MicroPython
    # (e.g. powered from the Freenove breakout). Best choice: no lost bytes, no reset circuit.
    native = [p.device for p in ports if p.vid == VID_ESPRESSIF and p.pid == 0x4001]
    wch = [p.device for p in ports if p.vid == VID_WCH and p.pid in PIDS_WCH]
    cp = [p.device for p in ports if p.vid == VID_CP210X]
    for found in (native, wch, cp):
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            say("ERROR: more than one possible ESP32 port:", found, "- pass --port.")
            sys.exit(2)
    if any(p.vid == VID_ESPRESSIF and p.pid == 0x1001 for p in ports):
        say("ERROR: only the ESP32's native \"USB\" port is connected. It is for flashing only")
        say("(the board starts in download mode there). Move the cable to the \"COM\" port.")
    else:
        say("ERROR: no ESP32 port found. Is the board plugged into its \"COM\" port?")
    say("Ports seen:", ["%s %04x:%04x" % (p.device, p.vid, p.pid) for p in ports if p.vid] or "none")
    sys.exit(2)


def install_pacing(port):
    """Pace every serial write for CH343 ports (see the top of this file)."""
    env = os.environ.get("ESP32_PACE")
    if env == "0" or (env != "1" and port_vid(port) != VID_WCH):
        return
    import serial

    if getattr(serial.Serial.write, "_paced", False):
        return
    orig_write = serial.Serial.write
    chunk = 64
    per_byte = 10.0 / BAUD * 1.25   # 10 bits per byte, +25% margin
    state = {"free_at": 0.0}

    def paced_write(self, data):
        data = bytes(data)
        sent = 0
        for i in range(0, len(data), chunk):
            part = data[i:i + chunk]
            wait = state["free_at"] - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            sent += orig_write(self, part) or 0
            state["free_at"] = time.monotonic() + len(part) * per_byte
        return sent

    paced_write._paced = True
    serial.Serial.write = paced_write


def process_list():
    """Lines of 'PID command line' for every process."""
    if WINDOWS:
        ps = ("Get-CimInstance Win32_Process | "
              "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }")
        return subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                              capture_output=True, text=True).stdout
    return subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout


def other_board_processes(port):
    """PIDs of mpremote processes using this port (or auto-connecting) and of `esp32.py run`."""
    me = os.getpid()
    out = process_list()
    pids = []
    for line in out.splitlines():
        pid_s, _, cmd = line.strip().partition(" ")
        if not pid_s.isdigit():
            continue
        pid = int(pid_s)
        if pid in (me, os.getppid()):
            continue
        if "esp32.py run" in cmd:
            pids.append(pid)
        elif "mpremote" in cmd and "devs" not in cmd and (port in cmd or "connect" not in cmd):
            pids.append(pid)
    return pids


def kill_local(port):
    pids = other_board_processes(port)
    # SIGKILL does not exist on Windows; there os.kill(SIGTERM) is TerminateProcess (also a hard kill).
    for sig in (getattr(signal, "SIGKILL", signal.SIGTERM),):  # no cleanup wanted: we stop it ourselves
        for pid in pids:
            try:
                os.kill(pid, sig)
                say("ended local process", pid)
            except ProcessLookupError:
                pass
    if pids:
        time.sleep(0.3)


def open_port(port):
    import serial  # pyserial, installed with mpremote

    last = None
    for _ in range(20):  # up to ~2 s for a killed process to release the port
        try:
            # DTR = RTS = 1 before and after open: the ESP32 is not reset (same as mpremote).
            ser = serial.Serial()
            ser.port, ser.baudrate, ser.timeout = port, BAUD, 0.05
            ser.dtr = ser.rts = True
            if not WINDOWS:
                ser.exclusive = True
            ser.open()
            return ser
        except (OSError, serial.SerialException) as e:
            last = e
            time.sleep(0.1)
    say("ERROR: cannot open", port, "-", last)
    say("Is Thonny, screen or another terminal using it? Close it and run STOP again.")
    return None


def read_for(ser, seconds, until=None):
    data = b""
    end = time.time() + seconds
    while time.time() < end:
        chunk = ser.read(256)
        if chunk:
            data += chunk
            if until and any(u in data for u in until):
                break
    return data


def show(data):
    text = data.replace(b"\x04", b"").decode("utf-8", "replace").strip()
    for line in text.splitlines():
        say("board:", line)


def stop_board(port):
    ser = open_port(port)
    if ser is None:
        return False
    try:
        prompts = (b">>>", b"\x04>", b"raw REPL")
        ok = False
        for attempt in range(3):
            # One Ctrl-C at a time: a second one too soon could interrupt the finally block.
            ser.write(b"\x03")
            data = read_for(ser, 1.5, until=prompts)
            show(data)
            if any(p in data for p in prompts):
                ok = True
                break
            say("no prompt yet, sending Ctrl-C again")
        # Back to the normal REPL (harmless if already there), then check the board is idle.
        ser.write(b"\r\x02")
        read_for(ser, 0.3)
        ser.write(b"\r")
        data = read_for(ser, 1.0)
        idle = data.strip().endswith(b">>>")
        if ok and idle:
            say("STOPPED: program interrupted, board idle at the >>> prompt.")
            return True
        show(data)
        say("WARNING: could not confirm the stop. Use the power switch if the motors still run.")
        return False
    finally:
        ser.close()


def cmd_stop(port):
    kill_local(port)
    return 0 if stop_board(port) else 1


def start_key_reader():
    """Read lines typed in this terminal on a background thread; returns a queue of bytes."""
    q = queue.Queue()

    def reader():
        try:
            for line in sys.stdin:
                # Drop control characters: Ctrl-C/Ctrl-D bytes would interrupt or reset the board.
                clean = "".join(ch for ch in line if ch >= " ")
                q.put((clean + "\n").encode("utf-8", "replace"))
        except (OSError, ValueError, EOFError):
            pass

    threading.Thread(target=reader, daemon=True).start()
    return q


def cmd_run(port, path):
    if not os.path.isfile(path):
        say("ERROR: no such file:", path)
        return 2
    try:
        from mpremote.transport_serial import SerialTransport
    except ImportError:
        say("ERROR: mpremote is not installed for", sys.executable, "- run: pip install mpremote")
        return 2
    with open(path, "rb") as f:
        code = f.read()

    stopping = {"why": None}
    signals = [s for s in ("SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK") if hasattr(signal, s)]
    signals = [getattr(signal, s) for s in signals]

    def on_signal(signum, _frame):
        stopping["why"] = signal.Signals(signum).name

    for s in signals:
        signal.signal(s, on_signal)

    try:
        board = SerialTransport(port, baudrate=115200)
    except Exception as e:
        say("ERROR: cannot open", port, "-", e)
        say("Is Thonny, screen or another terminal using it? Close it and try again.")
        return 2

    say("running", os.path.basename(path), "on", port,
        "- type a line + Enter to send it to the program; Ctrl+C here stops it (motors off).")
    ended = False
    err = b""
    try:
        # Same steps as `mpremote run`: interrupt, soft reset, raw REPL, send the file.
        board.enter_raw_repl(soft_reset=True)
        board.exec_raw_no_follow(code)
        keys = start_key_reader()
        ser = board.serial
        section = 0  # 0 = program output, 1 = error output; each ends with \x04
        tail = b""   # last bytes seen, to spot the ROM boot banner after an unexpected reset
        reset_seen_at = None
        while stopping["why"] is None:
            if reset_seen_at and time.time() - reset_seen_at > 1.5:
                say("WARNING: the ESP32 rebooted during the program (see ESP-ROM log above).")
                say("rst:0x1 POWERON usually means a supply dip or the RST button. Program is not running.")
                board.close()
                return 1
            n = ser.in_waiting
            if n:
                data = ser.read(n)
                if reset_seen_at is None and b"ESP-ROM:" in tail + data:
                    reset_seen_at = time.time()  # let the boot log finish printing first
                tail = (tail + data)[-16:]
                while data:
                    k = data.find(b"\x04")
                    part = data if k < 0 else data[:k]
                    if section == 0:
                        try:
                            sys.stdout.buffer.write(part)
                            sys.stdout.flush()
                        except (OSError, ValueError):
                            pass
                    else:
                        err += part
                    if k < 0:
                        break
                    data = data[k + 1:]
                    section += 1
                    if section == 2:
                        ended = True
                        break
                if ended:
                    break
            else:
                time.sleep(0.01)
            while not keys.empty():
                ser.write(keys.get())
    except Exception as e:
        if stopping["why"] is None:
            say("ERROR while running:", repr(e))

    if ended:
        # The program finished by itself (or stopped with an error, printed below).
        if err:
            show_text = err.decode("utf-8", "replace").rstrip()
            try:
                print(show_text, flush=True)
            except (OSError, ValueError):
                pass
        try:
            board.exit_raw_repl()
        except Exception:
            pass
        board.close()
        return 1 if err else 0

    # Stopped by Ctrl+C / VS Code, or the connection failed: make sure the board is stopped.
    # Ignore further Ctrl+C while stopping, so the stop cannot be cut short.
    for s in signals:
        signal.signal(s, signal.SIG_IGN)
    try:
        board.close()
    except Exception:
        pass
    say("got", stopping["why"] or "an error", "- stopping the program on the ESP32...")
    return 0 if stop_board(port) else 1


def cmd_mp(port, args):
    """Run mpremote on PORT with paced writes: `mp ls` = `mpremote connect PORT ls`."""
    try:
        from mpremote.main import main as mpremote_main
    except ImportError:
        say("ERROR: mpremote is not installed for", sys.executable, "- run: pip install mpremote")
        return 2
    sys.argv = ["mpremote", "connect", port] + args
    return mpremote_main()


def main(argv):
    port = None
    if argv[:1] != ["mp"] and "--port" in argv:
        i = argv.index("--port")
        port = argv[i + 1]
        del argv[i:i + 2]
    elif argv[1:3] and argv[1] == "--port":  # mp --port PORT ...
        port = argv[2]
        del argv[1:3]
    if argv[:1] == ["port"]:
        print(pick_port(port))
        return 0
    if argv[:1] in (["stop"], ["run"], ["mp"]):
        port = pick_port(port)
        install_pacing(port)
    if argv[:1] == ["stop"]:
        return cmd_stop(port)
    if len(argv) == 2 and argv[0] == "run":
        return cmd_run(port, argv[1])
    if len(argv) >= 2 and argv[0] == "mp":
        return cmd_mp(port, argv[1:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
