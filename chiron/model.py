"""What every check returns, and how results combine into a verdict."""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Status(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    NA = "n/a"    # not present or not measurable here (no battery in a desktop, no sensors in a VM)
    INFO = "info"  # facts without a verdict (inventory)


_RANK = {Status.RED: 3, Status.YELLOW: 2, Status.GREEN: 1, Status.INFO: 0, Status.NA: 0}


def worst(statuses, default=Status.NA):
    """The most serious status in the list (red > yellow > green > info/n/a)."""
    statuses = list(statuses)
    if not statuses:
        return default
    best = max(statuses, key=lambda s: _RANK[s])
    if _RANK[best] > 0:
        return best
    return Status.INFO if Status.INFO in statuses else Status.NA


@dataclass
class Result:
    area: str                 # stable id, e.g. "battery" (used by history/compare)
    title: str                # e.g. "Battery health"
    status: Status
    summary: str              # one line, technical English
    evidence: dict = field(default_factory=dict)
    owner: tuple = None       # (message key, params) for the owner summary, or None to leave it out

    def to_dict(self):
        return {"area": self.area, "title": self.title, "status": self.status.value,
                "summary": self.summary, "evidence": self.evidence,
                "owner": {"key": self.owner[0], "params": self.owner[1]} if self.owner else None}


@dataclass
class Context:
    """Shared by all checks during one run."""
    raw_dir: Path = None      # raw tool outputs are saved here (report folder /raw)
    quick: bool = False       # skip slow parts (disk speed test)
    own: set = field(default_factory=set)  # the stick's own disks, never checked or touched

    def save_raw(self, name, text):
        if self.raw_dir and text:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            (self.raw_dir / name).write_text(text if text.endswith("\n") else text + "\n")
