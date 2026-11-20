"""lift_web.py - scissor lift controlled from a phone over Wi-Fi (standalone test)

MicroPython v1.29 on the ESP32-S3. Run with `python3 tools/esp32.py run lift_web.py`
(VS Code: open this file, Cmd+Shift+B). Stop with Ctrl+C in that terminal or the STOP task.

The ESP32 creates its own Wi-Fi network (AP_NAME / AP_PASSWORD below) and serves a page at
http://192.168.4.1 with hold-to-run UP / DOWN buttons and a STOP button.

Wiring:
  GPIO 14 -> MD10C PWM      GPIO 13 -> MD10C DIR      ESP32 G -> MD10C GND (shared ground)
  Lift encoder A (yellow, through 10k/20k divider) -> GPIO 42 (used for the stall check)
  Optional limit switches: see TOP_LIMIT_PIN / BOTTOM_LIMIT_PIN below.

Safety:
  - The lift only runs while a button is held. The page repeats the command every 150 ms;
    if nothing arrives for TIMEOUT_MS (phone locked, Wi-Fi dropped, page closed) it stops.
  - Stopping is immediate. Starting ramps up. DIR is only changed while the power is 0.
  - Stops if lift encoder A gets no pulses at full power (stuck / end of travel), and at a
    pressed limit switch. After those, let go of the button before it will move again.
  - The wheel motors are held off the whole time (wheels and lift never run together).
  - Ctrl+C / STOP: the finally block turns the lift off and switches the Wi-Fi off.
"""
from machine import Pin, PWM
import network
import time
import asyncio

# ======================= Settings =======================
AP_NAME     = "BagLift"      # Wi-Fi network the ESP32 creates
AP_PASSWORD = "followme123"  # Wi-Fi password (at least 8 characters)
LIFT_SPEED  = 40     # % lift power while a button is held. Keep it low until the lift is tested
LIFT_RAMP   = 10.0   # most the lift power can rise per 0.1 s (%). Stopping is always immediate
UP_DIR      = 0      # MD10C DIR value that moves the lift UP (0 or 1). Same as LIFT_UP_DIR in follow_me.py
TIMEOUT_MS  = 500    # stop if no UP/DOWN command arrives for this long (ms)
STALL_CHECK = True   # stop if lift encoder A gets no pulses at full power. False for the test without the MD10C
STALL_READS = 3      # this many 0.1 s readings in a row with 0 pulses on encoder A = stalled
TOP_LIMIT_PIN    = None  # GPIO of the top limit switch (for example 6), None = no switch
BOTTOM_LIMIT_PIN = None  # GPIO of the bottom limit switch (for example 7), None = no switch
LIMIT_PRESSED    = 1     # pin value when a switch is pressed: 1 = NC switch to GND (recommended), 0 = NO switch

LOOP_MS   = 50     # lift control step (ms)
FILTER_NS = 10000  # encoder glitch filter: ignore pulses shorter than 10 us
HTTP_PORT = 80

# ======================= Lift motor (MD10C) =======================
pwm_lift = PWM(Pin(14), freq=1000, duty_u16=0)
dir_lift = Pin(13, Pin.OUT, value=UP_DIR)

# ======================= Wheels: held OFF for this whole program =======================
wheel_pwms = [PWM(Pin(p), freq=1000, duty_u16=0) for p in (18, 10)]
wheel_dirs = [Pin(p, Pin.OUT, value=0) for p in (8, 9, 11, 12)]


def all_off():
    pwm_lift.duty_u16(0)
    for p in wheel_pwms:
        p.duty_u16(0)
    for p in wheel_dirs:
        p.value(0)


def set_lift(p):
    p = max(0, min(100, p))
    pwm_lift.duty_u16(int(p * 655))


# ======================= Lift encoder A (stall check) =======================
enc_a = Pin(42, Pin.IN, Pin.PULL_UP)
try:
    from machine import Counter
    cnt_a = Counter(2, enc_a, edge=Counter.RISING, filter_ns=FILTER_NS)  # wheels use 0 and 1

    def read_a():
        n = cnt_a.value()
        cnt_a.value(0)
        return n
except Exception as e:
    print("Hardware counter not available (", repr(e), ") - using an interrupt")
    _count_a = 0

    def _irq_a(pin):
        global _count_a
        _count_a += 1

    enc_a.irq(trigger=Pin.IRQ_RISING, handler=_irq_a)

    def read_a():
        global _count_a
        n = _count_a
        _count_a = 0
        return n

# ======================= Limit switches (optional) =======================
top_sw = Pin(TOP_LIMIT_PIN, Pin.IN, Pin.PULL_UP) if TOP_LIMIT_PIN is not None else None
bottom_sw = Pin(BOTTOM_LIMIT_PIN, Pin.IN, Pin.PULL_UP) if BOTTOM_LIMIT_PIN is not None else None


def at_limit(going_up):
    sw = top_sw if going_up else bottom_sw
    return sw is not None and sw.value() == LIMIT_PRESSED


# ======================= Shared state =======================
want = None          # "up" / "down" while a button is held, else None
latched = False      # True after a stall / limit stop: ignore UP/DOWN until the button is let go
last_cmd = time.ticks_ms()
last_reason = ""     # why the lift last stopped (shown on the page)
power = 0.0          # current lift power (%)
seen = {}            # page id -> last command number (drops requests that arrive out of order)
ap = None
server = None


def halt(why, latch=False):
    """Stop the lift now and print why."""
    global want, latched, power, last_reason
    pwm_lift.duty_u16(0)
    power = 0.0
    if want:
        print("LIFT: STOP (" + why + ")")
    want = None
    latched = latch
    last_reason = why


def status_text():
    if want:
        s = "Moving " + want.upper() + " " + str(round(power)) + "%"
    elif latched:
        s = "Stopped: " + last_reason + ". Let go of the button."
    else:
        s = "Stopped" + (" (" + last_reason + ")" if last_reason else "")
    if top_sw is not None and top_sw.value() == LIMIT_PRESSED:
        s += " | top switch pressed"
    if bottom_sw is not None and bottom_sw.value() == LIMIT_PRESSED:
        s += " | bottom switch pressed"
    return s


def command(d, cid, n):
    global want, last_cmd, latched
    if cid:
        if n <= seen.get(cid, -1):
            return  # older than a command we already handled from this page
        if cid not in seen and len(seen) >= 8:
            seen.clear()
        seen[cid] = n
    if d == "stop":
        halt("button released")
        latched = False
    elif d in ("up", "down"):
        last_cmd = time.ticks_ms()
        if not latched:
            want = d


# ======================= Lift control loop =======================
async def lift_loop():
    global power, latched
    step = LIFT_RAMP * LOOP_MS / 100
    moving = None
    zero_run = 0
    total_a = 0
    last_check = time.ticks_ms()
    last_print = last_check
    while True:
        now = time.ticks_ms()

        # hold-to-run: no command for TIMEOUT_MS -> stop (also ends a stall/limit latch)
        if (want or latched) and time.ticks_diff(now, last_cmd) > TIMEOUT_MS:
            halt("timeout: no command for " + str(TIMEOUT_MS) + " ms")
            latched = False

        if want and at_limit(want == "up"):
            halt(("top" if want == "up" else "bottom") + " limit switch", latch=True)

        if want is None:
            power = 0.0
        else:
            d = UP_DIR if want == "up" else 1 - UP_DIR
            if dir_lift.value() != d:
                if power > 0:
                    power = 0.0  # cut first; DIR changes on the next step
                else:
                    dir_lift.value(d)
            else:
                power = min(float(LIFT_SPEED), power + step)
        set_lift(power)

        if want != moving:
            if want:
                print("LIFT:", want.upper())
                total_a = 0
                last_print = now
            moving = want
            zero_run = 0

        # stall check every 0.1 s, only while running at full lift power
        if time.ticks_diff(now, last_check) >= 100:
            last_check = now
            a = read_a()
            total_a += a
            if want and power >= LIFT_SPEED:
                zero_run = zero_run + 1 if a == 0 else 0
                if STALL_CHECK and zero_run >= STALL_READS:
                    halt("STALL: no pulses on encoder A (stuck, end of travel, or encoder wiring)",
                         latch=True)
            else:
                zero_run = 0

        if want and time.ticks_diff(now, last_print) >= 1000:
            last_print = now
            print("LIFT", want.upper(), " power:", round(power), "%  encoder A total:", total_a)

        await asyncio.sleep(LOOP_MS / 1000)


# ======================= Web server =======================
PAGE = b"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>Bag lift</title>
<style>
body{margin:0;font-family:-apple-system,system-ui,sans-serif;background:#111;color:#eee;text-align:center;
-webkit-user-select:none;user-select:none;-webkit-touch-callout:none}
h1{font-size:22px;margin:16px 0 4px}
#st{font-size:18px;margin:8px 16px 12px;min-height:2.4em}
#st.bad{color:#ff8a80}
button{display:block;width:calc(100% - 32px);margin:12px 16px;height:22vh;font-size:34px;font-weight:700;
border:0;border-radius:16px;color:#fff;touch-action:none;-webkit-user-select:none;user-select:none;
-webkit-touch-callout:none}
#up{background:#2a7d3c}#down{background:#2457a6}#stop{background:#b3261e;height:14vh}
button.on{filter:brightness(1.4);outline:4px solid #fff}
p{color:#999;font-size:14px;margin:8px 16px}
</style></head><body>
<h1>Bag lift</h1>
<div id="st">Connecting...</div>
<button id="up">UP</button>
<button id="down">DOWN</button>
<button id="stop">STOP</button>
<p>Hold UP or DOWN to move. Let go to stop.</p>
<script>
var cid=Math.random().toString(36).slice(2,8),n=0,held=null,busy=false,tick=null;
var st=document.getElementById('st');
function show(t,ok){st.textContent=t;st.className=ok?'':'bad';}
function get(url,gated){
 if(gated){if(busy)return;busy=true;}
 var x=new XMLHttpRequest();x.open('GET',url);x.timeout=400;
 x.onload=function(){show(x.responseText,true);};
 x.onerror=x.ontimeout=function(){show('No reply from the bag. Check the Wi-Fi.',false);};
 x.onloadend=function(){if(gated)busy=false;};
 x.send();
}
function send(d){n++;get('/cmd?d='+d+'&c='+cid+'&n='+n,d!='stop');}
function press(d,e){
 e.preventDefault();if(held==d)return;release();
 held=d;document.getElementById(d).className='on';send(d);
 tick=setInterval(function(){if(held)send(held);},150);
}
function release(){
 if(!held)return;clearInterval(tick);tick=null;
 document.getElementById(held).className='';held=null;send('stop');
}
['up','down'].forEach(function(d){
 var b=document.getElementById(d);
 b.addEventListener('pointerdown',function(e){press(d,e);});
 ['pointerup','pointercancel','pointerleave'].forEach(function(ev){b.addEventListener(ev,release);});
 b.addEventListener('contextmenu',function(e){e.preventDefault();});
});
document.getElementById('stop').addEventListener('pointerdown',function(e){e.preventDefault();release();send('stop');});
document.addEventListener('visibilitychange',function(){if(document.hidden)release();});
window.addEventListener('blur',release);
window.addEventListener('pagehide',release);
setInterval(function(){if(!held)get('/status',true);},1000);
get('/status',true);
</script></body></html>
"""


def query(path):
    out = {}
    if "?" in path:
        for kv in path.split("?", 1)[1].split("&"):
            kv = kv.split("=", 1)
            out[kv[0]] = kv[1] if len(kv) > 1 else ""
    return out


def response(code, ctype, body):
    head = ("HTTP/1.1 " + code + "\r\nContent-Type: " + ctype +
            "\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: " +
            str(len(body)) + "\r\n\r\n")
    return head.encode() + body


async def handle(reader, writer):
    try:
        line = await asyncio.wait_for(reader.readline(), 2)
        while True:  # skip the request headers
            h = await asyncio.wait_for(reader.readline(), 2)
            if not h or h == b"\r\n":
                break
        parts = line.split()
        path = parts[1].decode() if len(parts) > 1 else "/"
        if path.startswith("/cmd"):
            q = query(path)
            try:
                n = int(q.get("n", "0"))
            except ValueError:
                n = 0
            command(q.get("d", ""), q.get("c", ""), n)
            out = response("200 OK", "text/plain; charset=utf-8", status_text().encode())
        elif path.startswith("/status"):
            out = response("200 OK", "text/plain; charset=utf-8", status_text().encode())
        elif path == "/" or path.startswith("/?"):
            out = response("200 OK", "text/html; charset=utf-8", PAGE)
        else:
            out = response("404 Not Found", "text/plain", b"not found")
        writer.write(out)
        await writer.drain()
    except Exception as e:
        if not isinstance(e, (OSError, asyncio.TimeoutError)):
            print("web error:", repr(e))
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ======================= Wi-Fi access point =======================
def start_ap():
    if len(AP_PASSWORD) < 8:
        raise ValueError("AP_PASSWORD must be at least 8 characters")
    network.WLAN(network.STA_IF).active(False)
    w = network.WLAN(network.AP_IF)
    w.active(True)
    try:
        w.config(ssid=AP_NAME, key=AP_PASSWORD, security=network.AUTH_WPA2_PSK)
    except (TypeError, ValueError):
        # older keyword names
        w.config(essid=AP_NAME, key=AP_PASSWORD, authmode=network.AUTH_WPA2_PSK)
    for _ in range(50):
        if w.active():
            break
        time.sleep_ms(100)
    try:
        ip = w.ipconfig("addr4")[0]
    except Exception:
        ip = w.ifconfig()[0]
    return w, ip


async def main():
    global ap, server
    ap, ip = start_ap()
    server = await asyncio.start_server(handle, "0.0.0.0", HTTP_PORT)
    print("Lift website ready. Join Wi-Fi", AP_NAME, "(password " + AP_PASSWORD + "), open http://" + ip)
    print("UP_DIR =", UP_DIR, " LIFT_SPEED =", LIFT_SPEED, "%  STALL_CHECK =", STALL_CHECK,
          " limits: top", TOP_LIMIT_PIN, "bottom", BOTTOM_LIMIT_PIN)
    await lift_loop()


try:
    all_off()
    asyncio.new_event_loop()  # fresh event loop, in case an earlier run left one behind
    asyncio.run(main())
finally:
    all_off()
    try:
        if server:
            server.close()
    except Exception:
        pass
    try:
        if ap:
            ap.active(False)
    except Exception:
        pass
    print("Lift stopped (motor off), Wi-Fi off")
