"""The report's checks. Each module has run(ctx) -> list[Result] and never raises:
a check that breaks becomes one "n/a" result instead of stopping the report."""
import traceback

from chiron.model import Result, Status

# Report order (owner summary and report follow it)
MODULES = ["system", "battery", "storage", "memory", "cpu", "sensors",
           "kernel_log", "devices", "diskspace", "win11"]
TITLES = {"system": "System", "battery": "Battery", "storage": "Storage", "memory": "Memory", "cpu": "CPU",
          "sensors": "Sensors", "kernel_log": "Kernel log", "devices": "Devices", "diskspace": "Disk space",
          "win11": "Windows 11"}


def run_all(ctx, only=None, progress=print, on_check=None, on_result=None):
    """on_check(module) before each module, on_result(module, result) for each of its results
    (the doctor launcher lights its stars from these)."""
    import importlib
    results = []
    for name in MODULES:
        if only and name not in only:
            continue
        progress(f"  checking {name.replace('_', ' ')}…")
        if on_check:
            on_check(name)
        try:
            mod = importlib.import_module(f"chiron.checks.{name}")
            found = mod.run(ctx)
        except Exception:  # noqa: BLE001 - a broken check must not stop the report
            ctx.save_raw(f"error-{name}.txt", traceback.format_exc())
            found = [Result(name, TITLES[name], Status.NA, "This check failed to run (details in raw/).",
                            {"error": traceback.format_exc(limit=1).strip().splitlines()[-1]})]
        results.extend(found)
        if on_result:
            for r in found:
                on_result(name, r)
    return results
