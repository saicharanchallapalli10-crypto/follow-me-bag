#!/usr/bin/env python3
"""Run and stop MicroPython programs on the ESP32 (macOS, mpremote).

    python3 tools/esp32.py run <file.py> [--port PORT]
    python3 tools/esp32.py stop [--port PORT]

Why this exists: when `mpremote run` gets Ctrl+C it only exits on the Mac. It never sends
Ctrl-C to the board, so the program (and the motors) keep running on the ESP32.

run:  starts `mpremote connect PORT run FILE`. Ctrl+C in the terminal, or VS Code closing
      the task, ends mpremote and then sends the stop sequence below.
stop: ends any mpremote/run process using the ESP32, opens the port, sends ONE Ctrl-C
      (KeyboardInterrupt -> the program's finally block turns the motors off), waits for
      the REPL prompt, and checks the board has gone quiet.

Port: --port, else $ESP32_PORT, else /dev/cu.usbserial-130. If that port does not exist
and exactly one /dev/cu.usbserial-* port exists, that one is used.

Windows (use `python` instead of `python3`): port is --port or $ESP32_PORT (e.g. COM5),
else the only CP210x (Silicon Labs) COM port. The Windows branches below are marked
`if WINDOWS:`; the macOS code paths are unchanged from the hardware-tested version.
"""
import glob
import os
import signal
import subprocess
import sys
import time

DEFAULT_PORT = "/dev/cu.usbserial-130"
WINDOWS = os.name == "nt"


def say(*args):
    # The terminal may already be gone (VS Code closed the task); never crash on print.
    try:
        print("[esp32]", *args, flush=True)
    except (OSError, ValueError):
        pass


def pick_port(arg_port):
    if arg_port:
        return arg_port
    if WINDOWS:
        return pick_port_windows()
    port = os.environ.get("ESP32_PORT", DEFAULT_PORT)
    if os.path.exists(port):
        return port
    found = glob.glob("/dev/cu.usbserial-*")
    if len(found) == 1:
        say("note:", port, "not found, using", found[0])
        return found[0]
    say("ERROR: ESP32 port", port, "not found. usbserial ports:", found or "none")
    say("Run `mpremote devs` and pass --port.")
    sys.exit(2)


def pick_port_windows():
    # COM ports are not files, so os.path.exists() cannot check them: trust $ESP32_PORT.
    port = os.environ.get("ESP32_PORT")
    if port:
        return port
    from serial.tools import list_ports  # pyserial, installed with mpremote

    found = [p.device for p in list_ports.comports() if p.vid == 0x10C4]  # CP2102N on the DevKit
    if len(found) == 1:
        say("using", found[0])
        return found[0]
    say("ERROR: could not pick the ESP32 port. CP210x ports found:", found or "none")
    say("Run `mpremote devs` and pass --port COMx (or set ESP32_PORT).")
    sys.exit(2)


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
            # Same way mpremote opens it on macOS, so the ESP32 is not reset.
            return serial.Serial(port, 115200, timeout=0.05, exclusive=True)
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


def cmd_run(port, path):
    if not os.path.isfile(path):
        say("ERROR: no such file:", path)
        return 2
    say("running", os.path.basename(path), "on", port, "- Ctrl+C here stops it (motors off).")
    # Own session: Ctrl+C reaches only this wrapper, which then stops mpremote AND the board.
    args = [sys.executable, "-m", "mpremote", "connect", port, "run", path]
    if WINDOWS:
        child = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        child = subprocess.Popen(args, stdin=subprocess.DEVNULL, start_new_session=True)
    stopping = {"why": None}
    signals = [s for s in ("SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK") if hasattr(signal, s)]
    signals = [getattr(signal, s) for s in signals]

    def on_signal(signum, _frame):
        stopping["why"] = signal.Signals(signum).name
        try:
            child.kill()
        except ProcessLookupError:
            pass

    for s in signals:
        signal.signal(s, on_signal)

    while True:
        try:
            # On Windows a blocking wait() cannot be interrupted by Ctrl+C, so poll there.
            rc = child.wait(timeout=0.2) if WINDOWS else child.wait()
            break
        except (InterruptedError, subprocess.TimeoutExpired):
            continue

    if stopping["why"] is None:
        return rc  # program ended by itself (or an error was printed)

    # Ignore further Ctrl+C while stopping, so the stop cannot be cut short.
    for s in signals:
        signal.signal(s, signal.SIG_IGN)
    say("got", stopping["why"], "- stopping the program on the ESP32...")
    return 0 if stop_board(port) else 1


def main(argv):
    port = None
    if "--port" in argv:
        i = argv.index("--port")
        port = argv[i + 1]
        del argv[i:i + 2]
    if len(argv) >= 1 and argv[0] == "stop":
        return cmd_stop(pick_port(port))
    if len(argv) == 2 and argv[0] == "run":
        return cmd_run(pick_port(port), argv[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
