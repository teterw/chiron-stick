"""CPU: model, cores, clocks, idle temperature against the CPU's own limit (Tjmax).
Behaviour under load (temperature, throttling) is measured by `chiron stress`."""
import re
from pathlib import Path

from chiron.checks.sensors import cpu_temp, readings
from chiron.model import Result, Status
from chiron.util import read, read_int


def cpu_model():
    for line in (read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("model name"):
            return re.sub(r"\s+", " ", line.split(":", 1)[1]).strip()
    return "unknown"


def default_tjmax(model):
    """When the sensor driver doesn't expose the limit (k10temp never does): Intel parts are
    100 °C, AMD Ryzen 95 °C, except Zen 3 desktop chips (Ryzen 5000 without H/U) at 90 °C."""
    if "AMD" not in model:
        return 100
    m = re.search(r"Ryzen \d+ (\d)\d{3}([A-Z]*)", model)
    if m and m.group(1) == "5" and not m.group(2).startswith(("H", "U")):
        return 90
    return 95


def run(ctx):
    model = cpu_model()
    cpus = sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*"))
    max_khz = read_int("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    temps, _ = readings()
    idle, tjmax = cpu_temp(temps)
    tjmax_source = "sensor" if tjmax else "default for this CPU family"
    tjmax = tjmax or default_tjmax(model)
    ev = {"model": model, "threads": len(cpus), "max_mhz": round(max_khz / 1000) if max_khz else None,
          "governor": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
          "idle_temp_c": idle, "tjmax_c": tjmax, "tjmax_source": tjmax_source}
    if idle is None:
        return [Result("cpu", "CPU", Status.INFO, f"{model}, {len(cpus)} threads; no temperature sensor (VM?)", ev)]
    # Idle should sit far below the limit; close to it means cooling problems (dust, dried paste, fan)
    status = Status.GREEN if idle < tjmax - 30 else Status.YELLOW if idle < tjmax - 15 else Status.RED
    summary = f"{model}, {len(cpus)} threads; idle {idle} °C (limit {tjmax} °C)"
    return [Result("cpu", "CPU", status, summary, ev, (f"cpu_idle.{status.value}", {"temp": idle}))]
