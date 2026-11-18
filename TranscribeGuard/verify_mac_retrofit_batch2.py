#!/usr/bin/env python3
"""Launch verification for the Mac-retrofit Windows EXE rebuild.

Runs the packaged EXE five times under Wine on a private Xvfb display.
A run passes when the window is visibly drawn and the process is still
alive after a settle period. Results are appended to a JSONL file.
"""
import json
import os
import subprocess
import time

DISPLAY = ":98"
ROOT = os.path.expanduser("~/workspace/transcribe-guard")
DELIVERY = os.path.join(ROOT, "release", "TranscribeGuard")
OUTDIR = os.path.join(ROOT, "verify_mac_retrofit_batch2")
os.makedirs(OUTDIR, exist_ok=True)
OUT = os.path.join(OUTDIR, "results.jsonl")
ENV = dict(os.environ, DISPLAY=DISPLAY,
           WINEPREFIX=os.path.expanduser("~/workspace/wine-prefix"),
           WINEDEBUG="-all")
RUNS = 5
MAX_WAIT = 120

os.environ["DISPLAY"] = DISPLAY
from PIL import Image, ImageChops, ImageGrab  # noqa: E402


def alive():
    r = subprocess.run(["pgrep", "-f", "TranscribeGuard[.]exe"],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def free_mb():
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable"):
                return int(line.split()[1]) // 1024
    return 0


def kill_app():
    subprocess.run(["pkill", "-9", "-f", "TranscribeGuard[.]exe"],
                   capture_output=True)
    time.sleep(2)


def small_grab():
    return ImageGrab.grab().resize((640, 450)).convert("L")


def diff_ratio(a, b):
    diff = ImageChops.difference(a, b)
    hist = diff.histogram()
    return sum(hist[16:]) / (a.size[0] * a.size[1])


# Start a private Xvfb if :98 is not already serving.
if not os.path.exists(f"/tmp/.X11-unix/X{DISPLAY[1:]}"):
    subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", "1600x1000x24"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    time.sleep(2)

with open(OUT, "w") as f:
    f.write("")
results = []
for run in range(1, RUNS + 1):
    kill_app()
    waited = 0
    while free_mb() < 450 and waited < 120:
        time.sleep(5)
        waited += 5
    baseline = small_grab()
    log = os.path.join(OUTDIR, f"launch_run{run}.log")
    t0 = time.time()
    with open(log, "wb") as lf:
        subprocess.Popen(
            ["script", "-qec", "wine TranscribeGuard.exe", log + ".pty"],
            cwd=DELIVERY, env=ENV, stdout=lf, stderr=subprocess.STDOUT)
    drawn_at = None
    while time.time() - t0 < MAX_WAIT:
        time.sleep(1.0)
        try:
            changed = diff_ratio(small_grab(), baseline)
        except Exception:
            changed = 0
        if changed > 0.02:
            drawn_at = time.time() - t0
            break
        if not alive() and time.time() - t0 > 20:
            break
    ok = drawn_at is not None
    time.sleep(3)
    final_alive = alive()
    shot_path = os.path.join(OUTDIR, f"exe_run{run}.png")
    try:
        ImageGrab.grab().save(shot_path)
    except Exception:
        shot_path = ""
    fault = 0
    try:
        with open(log + ".pty", "rb") as fh:
            fault = fh.read().count(b"page fault")
    except OSError:
        pass
    res = {"run": run, "drawn": ok,
           "time_to_drawn_s": round(drawn_at, 1) if drawn_at else None,
           "alive_after_settle": final_alive, "page_faults": fault,
           "free_mb_before": free_mb(), "waited_for_memory_s": waited,
           "screenshot": shot_path}
    results.append(res)
    with open(OUT, "a") as fh:
        fh.write(json.dumps(res) + "\n")
    print(json.dumps(res), flush=True)
    kill_app()

succ = sum(1 for r in results if r["drawn"] and r["alive_after_settle"])
print(json.dumps({"summary": f"{succ}/{RUNS} launches OK",
                  "times_s": [r["time_to_drawn_s"] for r in results]}))
