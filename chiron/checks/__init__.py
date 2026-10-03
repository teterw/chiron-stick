"""The report's checks. Each module has run(ctx) -> list[Result] and never raises:
a check that breaks becomes one "n/a" result instead of stopping the report."""
import traceback

from chiron.model import Result, Status

# Report order (owner summary and report follow it)
MODULES = ["system", "battery", "storage", "memory", "cpu", "sensors",
           "kernel_log", "devices", "diskspace", "win11"]


def run_all(ctx, only=None, progress=print):
    import importlib
    results = []
    for name in MODULES:
        if only and name not in only:
            continue
        progress(f"  checking {name.replace('_', ' ')}…")
        try:
            mod = importlib.import_module(f"chiron.checks.{name}")
            results.extend(mod.run(ctx))
        except Exception:  # noqa: BLE001 - a broken check must not stop the report
            ctx.save_raw(f"error-{name}.txt", traceback.format_exc())
            results.append(Result(name, name.replace("_", " ").title(), Status.NA,
                                  "This check failed to run (details in raw/).",
                                  {"error": traceback.format_exc(limit=1).strip().splitlines()[-1]}))
    return results
