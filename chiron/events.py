"""Machine-readable progress for the doctor launcher (`chiron doctor`).

With --events, report/stress/full write one JSON object per line on stdout instead of text:
  start   {mode, machine, steps: [{id, title}], minutes}      what this run will do
  check   {id}                                                 a step started
  result  {id, result: {area, title, status, summary, …}}      one finding of that step
  tick    {id, t, total, temp, tjmax, mhz}                     CPU stress, every second
  log     {text}                                               anything else worth showing
  done    {overall, folder, compare, compare_with}             finished; the report is written
  stopped {}                                                   stopped on request
A line "stop" on stdin, or stdin closing, stops the run the way Ctrl-C does. The launcher runs
chiron as root through pkexec, so it can't send it a signal; and a launcher that crashes or is
closed never leaves a stress test running with nobody watching."""
import _thread
import json
import os
import sys
import threading


class Events:
    def __init__(self, out=None):
        self.enabled = out is not None
        self._out = out

    def emit(self, kind, **data):
        if self.enabled:
            self._out.write(json.dumps({"e": kind, **data}, default=str, ensure_ascii=False) + "\n")
            self._out.flush()

    def say(self, text):
        if self.enabled:
            self.emit("log", text=text.strip())
        else:
            print(text)


def watch_stop(stream, interrupt=_thread.interrupt_main):
    """Stop the run (KeyboardInterrupt in the main thread) on a "stop" line or end of input."""
    def loop():
        for line in stream:
            if line.strip() == "stop":
                break
        interrupt()
    t = threading.Thread(target=loop, name="chiron-stop", daemon=True)
    t.start()
    return t


def start():
    """Switch this process to events mode. stdout keeps only the events: everything else that is
    printed, by us or by the tools we run, goes to stderr."""
    sys.stdout.flush()
    out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    watch_stop(sys.stdin)
    return Events(out)
