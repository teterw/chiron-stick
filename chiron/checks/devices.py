"""Device support (CLAUDE.md feature 4): for each PCI/USB device, does it work, is there just no
Linux driver/firmware on this stick (not a hardware fault), or is the driver loaded but logging
errors (possible hardware fault)? Plus quick functional checks: Wi-Fi scan, Bluetooth, webcam, audio."""
import os
import re
from pathlib import Path

from chiron.checks.kernel_log import kernel_log
from chiron.model import Result, Status, worst
from chiron.util import read, sh

# PCI class code prefixes worth reporting (bridges, SMBus etc. often have no driver and that's fine)
IMPORTANT_PCI = {"03": "graphics", "02": "network", "0401": "audio", "0403": "audio", "0c03": "USB controller",
                 "01": "storage controller", "0805": "card reader", "0d11": "Bluetooth", "0400": "camera/capture",
                 "0480": "multimedia"}
ERROR_WORDS = re.compile(r"\b(error|failed|failure|timeout|timed out|hang|fault)\b", re.I)
FIRMWARE_MISSING = re.compile(r"(Direct firmware load for (\S+) failed|firmware: failed to load (\S+))")


def pci_devices():
    rc, out, _ = sh(["lspci", "-nnk"])
    devs, cur = [], None
    for line in out.splitlines():
        m = re.match(r"^([0-9a-f:.]+) (.+?) \[([0-9a-f]{4})\]: (.+)$", line)
        if m:
            cur = {"slot": m.group(1), "class": m.group(2), "code": m.group(3), "name": m.group(4), "driver": None}
            devs.append(cur)
        elif cur and "Kernel driver in use:" in line:
            cur["driver"] = line.split(":", 1)[1].strip()
    return devs


def pci_kind(code):
    return IMPORTANT_PCI.get(code) or IMPORTANT_PCI.get(code[:2])


def own_usb_ports(own_disks):
    """USB device ids (like '4-2') the stick's own disk hangs off, so it's never reported."""
    ports = set()
    for d in own_disks:
        path = os.path.realpath(f"/sys/block/{d}/device")
        ports |= set(re.findall(r"/(\d+-[\d.]+)(?=/|:)", path))
    return ports


def usb_devices(skip):
    devs = []
    for d in sorted(Path("/sys/bus/usb/devices").glob("*-*")):
        if ":" in d.name or d.name in skip or read(d / "bDeviceClass") == "09":
            continue  # interfaces, the stick itself, hubs
        ifaces = list(Path("/sys/bus/usb/devices").glob(f"{d.name}:*"))
        drivers = sorted({os.path.basename(os.path.realpath(i / "driver")) for i in ifaces if (i / "driver").exists()})
        name = " ".join(x for x in (read(d / "manufacturer"), read(d / "product")) if x) or \
               f"USB device {read(d / 'idVendor')}:{read(d / 'idProduct')}"
        devs.append({"port": d.name, "name": name, "id": f"{read(d / 'idVendor')}:{read(d / 'idProduct')}",
                     "drivers": drivers})
    return devs


def classify(devices_pci, devices_usb, log):
    """Sort devices into works / no driver here / driver warnings / driver errors.
    One or two error lines from a driver are often harmless chatter; 3+ suggest a real problem."""
    works, nodriver, warnings, errors = [], [], [], []
    lines = log.splitlines()
    for d in devices_pci:
        kind = pci_kind(d["code"])
        if not kind:
            continue
        label = f"{kind}: {d['name']}"
        if not d["driver"]:
            nodriver.append(label)
            continue
        mine = [l for l in lines if d["slot"] in l]
        if any(FIRMWARE_MISSING.search(l) for l in mine):
            nodriver.append(f"{label} (firmware missing on this stick)")
            continue
        bad = [l for l in mine if ERROR_WORDS.search(l)]
        entry = {"device": label, "driver": d["driver"], "examples": [l.strip()[:200] for l in bad[:3]]}
        if len(bad) >= 3:
            errors.append(entry)
        elif bad:
            warnings.append(entry)
        else:
            works.append(f"{label} ({d['driver']})")
    for d in devices_usb:
        (works if d["drivers"] else nodriver).append(f"USB: {d['name']}" + (f" ({', '.join(d['drivers'])})" if d["drivers"] else ""))
    return works, nodriver, warnings, errors


def functional():
    """Quick does-it-respond checks."""
    out = {}
    wifi = [n.name for n in Path("/sys/class/net").glob("*") if (n / "wireless").exists() or (n / "phy80211").exists()]
    out["wifi_interfaces"] = wifi
    if wifi:
        rc, o, _ = sh(["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list", "--rescan", "yes"], timeout=30)
        out["wifi_networks_seen"] = len([l for l in o.splitlines() if l.strip()]) if rc == 0 else None
    out["bluetooth_controllers"] = len(list(Path("/sys/class/bluetooth").glob("hci*")))
    cams = {read(v / "name") for v in Path("/sys/class/video4linux").glob("video*") if read(v / "index") == "0"}
    out["webcams"] = sorted(c for c in cams if c)
    cards = re.findall(r"^\s*\d+ \[\w+\s*\]: .* - (.+)$", read("/proc/asound/cards") or "", re.M)
    out["audio_cards"] = cards
    return out


def run(ctx):
    log = kernel_log()
    works, nodriver, warnings, errors = classify(pci_devices(), usb_devices(own_usb_ports(ctx.own)), log)
    func = functional()
    statuses = [Status.GREEN]
    if nodriver or warnings:
        statuses.append(Status.YELLOW)
    if errors:
        statuses.append(Status.RED)
    if func["wifi_interfaces"] and func.get("wifi_networks_seen") == 0:
        statuses.append(Status.YELLOW)
    status = worst(statuses)
    parts = [f"{len(works)} working"]
    if nodriver:
        parts.append(f"{len(nodriver)} with no driver on this stick (not a hardware fault)")
    if warnings:
        parts.append(f"{len(warnings)} with a few driver warnings: " + ", ".join(e["device"] for e in warnings))
    if errors:
        parts.append(f"{len(errors)} with driver errors: " + ", ".join(e["device"] for e in errors))
    if func["wifi_interfaces"]:
        seen = func.get("wifi_networks_seen")
        parts.append(f"Wi-Fi sees {seen} networks" if seen is not None else "Wi-Fi present (scan not possible)")
    parts.append(f"{len(func['webcams'])} webcam(s), {len(func['audio_cards'])} sound card(s), "
                 f"{func['bluetooth_controllers']} Bluetooth controller(s)")
    ev = {"works": works, "no_driver_here": nodriver, "driver_warnings": warnings, "driver_errors": errors, **func}
    return [Result("devices", "Devices", status, "; ".join(parts), ev,
                   (f"devices.{status.value}", {"n": len(nodriver), "what": ", ".join(e["device"] for e in errors)}))]
