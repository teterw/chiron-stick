"""`chiron stress`: how the machine holds up under load. CPU (temperature against its own limit,
clock speed, throttling, fans), a quick RAM test and a short GPU test.

Live safety limits (CLAUDE.md Phase 5): stops at once if the CPU stays above its own limit (Tjmax)
for more than 10 s, if a laptop on battery drops below 25%, or on Ctrl-C, and always kills its load
processes. The desktop theme's wallpaper rotation and compositor are paused first (clean results)."""
import csv
import io
import os
import re
import signal
import subprocess
import time
from pathlib import Path

from chiron import rice
from chiron.checks.cpu import cpu_model, default_tjmax
from chiron.checks.sensors import cpu_temp, readings
from chiron.model import Result, Status
from chiron.util import as_desktop_user, have, meminfo, read, read_int, sh

OVER_LIMIT_SECONDS = 10
MIN_BATTERY_PCT = 25


def cpu_mhz():
    freqs = [read_int(p) for p in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_cur_freq")]
    freqs = [f for f in freqs if f]
    return round(sum(freqs) / len(freqs) / 1000) if freqs else None


def throttle_count():
    total = 0
    for p in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/thermal_throttle/*_throttle_count"):
        total += read_int(p) or 0
    return total


def battery_state():
    for p in Path("/sys/class/power_supply").glob("*"):
        if read(p / "type") == "Battery" and read(p / "scope") != "Device":
            return read(p / "status"), read_int(p / "capacity")
    return None, None


def _avg(xs):
    xs = [x for x in xs if x]
    return sum(xs) / len(xs) if xs else None


def grade_cpu(max_temp, tjmax, drop, throttles, aborted):
    """CLAUDE.md Phase 5 table, against the CPU's own limit. Sitting at Tjmax is by design on many
    thin laptops: that alone is yellow. Red = over the limit, or clocks collapsing."""
    if aborted == "temp" or (max_temp is not None and max_temp > tjmax) or (drop is not None and drop > 25):
        return Status.RED
    if (max_temp is not None and max_temp >= tjmax - 2) or (drop is not None and drop >= 10) or throttles:
        return Status.YELLOW
    if max_temp is None and drop is None:
        return Status.INFO
    return Status.GREEN


def cpu_load(ctx, minutes, progress):
    if not have("stress-ng"):
        return [Result("cpu_load", "CPU under load", Status.NA, "stress-ng isn't installed")]
    tjmax = cpu_temp(readings()[0])[1] or default_tjmax(cpu_model())
    thr0 = throttle_count()
    proc = subprocess.Popen(["stress-ng", "--cpu", "0", "--cpu-method", "matrixprod", "--timeout", f"{int(minutes * 60)}s"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    samples, over_since, aborted = [], None, None
    start = time.monotonic()
    try:
        while proc.poll() is None:
            time.sleep(1)
            t = round(time.monotonic() - start)
            temps, fans = readings()
            temp = cpu_temp(temps)[0]
            mhz = cpu_mhz()
            bstatus, bcap = battery_state()
            samples.append({"t": t, "temp_c": temp, "mhz": mhz, "battery": bcap,
                            **{f"fan_{f['chip']}_{f['label']}": f["rpm"] for f in fans}})
            if temp is not None and temp > tjmax:
                over_since = over_since if over_since is not None else t
                if t - over_since > OVER_LIMIT_SECONDS:
                    aborted = "temp"
                    break
            else:
                over_since = None
            if bstatus == "Discharging" and bcap is not None and bcap < MIN_BATTERY_PCT:
                aborted = "battery"
                break
            if t % 15 == 0:
                progress(f"  {t:4d}s  CPU {temp if temp is not None else '?'} °C (limit {tjmax})  {mhz or '?'} MHz")
    except KeyboardInterrupt:
        aborted = "ctrl-c"
    finally:
        _stop(proc)

    if samples:
        buf = io.StringIO()
        keys = sorted({k for s in samples for k in s}, key=lambda k: (k != "t", k))
        w = csv.DictWriter(buf, fieldnames=keys)
        w.writeheader()
        w.writerows(samples)
        ctx.save_raw("stress-cpu.csv", buf.getvalue())
    temps = [s["temp_c"] for s in samples if s["temp_c"] is not None]
    max_temp = max(temps) if temps else None
    early = _avg(s["mhz"] for s in samples if 5 <= s["t"] <= 35)
    late = _avg(s["mhz"] for s in samples[-60:]) if len(samples) > 40 else None
    drop = round(100 * (early - late) / early) if early and late else None
    drop = max(drop, 0) if drop is not None else None
    throttles = throttle_count() - thr0
    status = grade_cpu(max_temp, tjmax, drop, throttles, aborted)
    reason = {"temp": f"stopped: CPU above its {tjmax} °C limit for over {OVER_LIMIT_SECONDS} s",
              "battery": f"stopped: battery below {MIN_BATTERY_PCT}% (plug the charger in)",
              "ctrl-c": "stopped with Ctrl-C"}.get(aborted)
    if aborted in ("battery", "ctrl-c"):
        status = Status.NA
    parts = [f"{len(samples)} s of full load", f"max {max_temp} °C (limit {tjmax} °C)" if max_temp is not None else "no CPU temperature sensor"]
    if early and late:
        parts.append(f"clock {round(early)} → {round(late)} MHz ({drop}% drop)")
    if throttles:
        parts.append(f"{throttles} thermal throttle events")
    if reason:
        parts.append(reason)
    ev = {"duration_s": len(samples), "max_temp_c": max_temp, "tjmax_c": tjmax, "clock_start_mhz": round(early) if early else None,
          "clock_end_mhz": round(late) if late else None, "clock_drop_pct": drop, "throttle_events": throttles, "aborted": aborted}
    results = [Result("cpu_load", "CPU under load", status, "; ".join(parts), {k: v for k, v in ev.items() if v is not None},
                      (f"cpu_load.{status.value}", {"max": max_temp, "drop": drop or 0}) if status in (Status.GREEN, Status.YELLOW, Status.RED) else None)]

    fan_keys = sorted({k for s in samples for k in s if k.startswith("fan_")})
    if fan_keys:
        peak = {k[4:]: max((s.get(k) or 0) for s in samples) for k in fan_keys}
        stopped = [k for k, v in peak.items() if v == 0]
        fstatus = Status.RED if stopped and len(samples) > 60 else Status.GREEN
        results.append(Result("fans", "Fans under load", fstatus,
                              ("not spinning: " + ", ".join(stopped)) if stopped else "all spinning: " + ", ".join(f"{k} {v} rpm" for k, v in peak.items()),
                              {"peak_rpm": peak}, ("fans.red", {}) if fstatus == Status.RED else None))
    return results


def _stop(proc):
    """Kill stress-ng and everything it started."""
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def ram_test(ctx):
    if not have("memtester"):
        return Result("ram_test", "RAM test", Status.NA, "memtester isn't installed")
    avail_mb = meminfo().get("MemAvailable", 0) // 1024
    size = max(64, min(1024, avail_mb // 4))
    rc, out, err = sh(["memtester", f"{size}M", "1"], timeout=1800)
    ctx.save_raw("memtester.txt", out + err)
    if "FAILURE" in out:
        return Result("ram_test", "RAM test", Status.RED, f"memtester found errors in {size} MB", {"size_mb": size}, ("ram_test.red", {}))
    if rc != 0:
        return Result("ram_test", "RAM test", Status.NA, f"memtester couldn't run ({(err or out).strip()[-120:]})", {"size_mb": size})
    return Result("ram_test", "RAM test", Status.GREEN, f"memtester passed on {size} MB (quick check; MemTest86 tests all of it)",
                  {"size_mb": size}, ("ram_test.green", {}))


def gpu_test(ctx):
    if not have("glmark2"):
        return Result("gpu", "Graphics", Status.NA, "glmark2 isn't installed")
    benches = [f"{b}:duration=4" for b in ("build", "texture", "shading", "bump", "effect2d", "pulsar", "refract")]
    cmd = ["glmark2", "--size", "800x600", *[x for b in benches for x in ("-b", b)]]
    rc, out, err = sh(as_desktop_user(cmd), timeout=150)
    ctx.save_raw("glmark2.txt", out + err)
    renderer = (re.search(r"GL_RENDERER:\s*(.+)", out) or [None, None])[1]
    score = (re.search(r"glmark2 Score:\s*(\d+)", out) or [None, None])[1]
    ev = {"renderer": renderer, "score": int(score) if score else None}
    if rc == 124:
        return Result("gpu", "Graphics", Status.RED, "the graphics test froze", ev, ("gpu.red", {}))
    if not score:
        if re.search(r"(cannot open display|Error: .*display|Failed to (open|initialize))", out + err, re.I):
            return Result("gpu", "Graphics", Status.NA, "no graphical session to run the test in", ev)
        return Result("gpu", "Graphics", Status.RED, f"the graphics test crashed (exit {rc})", ev, ("gpu.red", {}))
    if renderer and re.search(r"llvmpipe|softpipe|swrast", renderer):
        return Result("gpu", "Graphics", Status.YELLOW, f"no hardware acceleration ({renderer}), score {score}", ev, ("gpu.yellow", {}))
    return Result("gpu", "Graphics", Status.GREEN, f"{renderer}: score {score}", ev, ("gpu.green", {}))


def stress(ctx, minutes=10, gpu=True, ram=True, progress=print):
    """Run the load tests. Returns a list of Results."""
    bstatus, bcap = battery_state()
    if bstatus == "Discharging" and bcap is not None and bcap < MIN_BATTERY_PCT:
        return [Result("cpu_load", "CPU under load", Status.NA,
                       f"not started: battery at {bcap}% (plug the charger in for the stress test)")]
    if bstatus == "Discharging":
        progress("  note: running on battery; plug the charger in for a fair test (stops below 25%)")
    rice.pause()
    try:
        progress(f"  CPU: {minutes} min at full load (Ctrl-C stops it safely)")
        results = cpu_load(ctx, minutes, progress)
        if results[0].evidence.get("aborted") == "ctrl-c":
            return results  # the person wants to stop: don't start the next tests
        if ram:
            progress("  RAM: memtester quick pass")
            results.append(ram_test(ctx))
        if gpu:
            progress("  GPU: glmark2 short run")
            results.append(gpu_test(ctx))
        return results
    finally:
        rice.resume()
