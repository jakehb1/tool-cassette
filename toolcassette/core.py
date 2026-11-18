"""Record and replay tool calls for agent tests. Stdlib only."""
import functools
import hashlib
import json
import os
import time


class CassetteMiss(KeyError):
    """Raised in replay mode when a tool call isn't on the cassette."""


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def call_key(tool, args):
    """Stable key for a tool call: tool name + canonical JSON of its args."""
    h = hashlib.sha256((tool + "\x00" + _canon(args)).encode()).hexdigest()[:16]
    return "%s:%s" % (tool, h)


def load(path):
    """Read a cassette file (JSONL) into a list of entries."""
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except ValueError as e:
                raise ValueError("%s line %d: bad JSON (%s)" % (path, n, e))
    return entries


class Cassette:
    """Wrap tool functions so their calls are recorded to, or replayed from, a JSONL file.

    mode:
      "record"  call the real tool, overwrite the cassette with what happened
      "replay"  never call the real tool; unknown calls raise CassetteMiss
      "auto"    replay calls that are on the cassette, record the ones that aren't
    The default comes from the TOOL_CASSETTE env var, else "auto".
    """

    MODES = ("record", "replay", "auto")

    def __init__(self, path, mode=None):
        mode = mode or os.environ.get("TOOL_CASSETTE", "auto")
        if mode not in self.MODES:
            raise ValueError("mode must be one of %s, got %r" % (self.MODES, mode))
        self.path = path
        self.mode = mode
        self.stats = {"recorded": 0, "replayed": 0, "missed": 0}
        self._queues = {}  # key -> list of entries, consumed in order
        if mode == "record":
            d = os.path.dirname(os.path.abspath(path))
            os.makedirs(d, exist_ok=True)
            open(path, "w").close()
        else:
            for e in load(path):
                self._queues.setdefault(e["key"], []).append(e)
        self._seen = {}  # key -> how many times replayed (for repeated identical calls)

    def _append(self, entry):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(_canon(entry) + "\n")

    def call(self, tool, fn, args):
        key = call_key(tool, args)
        q = self._queues.get(key)
        if self.mode != "record" and q:
            i = self._seen.get(key, 0)
            entry = q[min(i, len(q) - 1)]  # repeat the last answer if called more times
            self._seen[key] = i + 1
            self.stats["replayed"] += 1
            if entry.get("error") is not None:
                raise RuntimeError(entry["error"])
            return entry["result"]
        if self.mode == "replay":
            self.stats["missed"] += 1
            raise CassetteMiss("%s(%s) is not on cassette %s; re-record with TOOL_CASSETTE=record"
                               % (tool, _canon(args), self.path))
        t0 = time.perf_counter()
        entry = {"key": key, "tool": tool, "args": args, "result": None, "error": None}
        try:
            entry["result"] = fn(**args)
            return entry["result"]
        except Exception as e:  # recorded so replays fail the same way
            entry["error"] = "%s: %s" % (type(e).__name__, e)
            raise
        finally:
            entry["ms"] = round((time.perf_counter() - t0) * 1000, 1)
            json.dumps(entry, default=str)  # fail loudly here, not on replay
            self._append(entry)
            self._queues.setdefault(key, []).append(entry)
            self._seen[key] = self._seen.get(key, 0) + 1
            self.stats["recorded"] += 1

    def tool(self, fn=None, name=None):
        """Decorator. Tools must be called with keyword arguments."""
        def wrap(f):
            tname = name or f.__name__

            @functools.wraps(f)
            def inner(**kwargs):
                return self.call(tname, f, kwargs)
            return inner
        return wrap(fn) if fn else wrap


def diff(old, new):
    """Compare two cassettes. Returns a list of (kind, tool, args, detail)."""
    a = {e["key"]: e for e in old}
    b = {e["key"]: e for e in new}
    out = []
    for k, e in a.items():
        if k not in b:
            out.append(("removed", e["tool"], e["args"], "no longer called"))
        else:
            f = b[k]
            if _canon(e.get("result")) != _canon(f.get("result")) or e.get("error") != f.get("error"):
                out.append(("changed", e["tool"], e["args"], _delta(e, f)))
    for k, f in b.items():
        if k not in a:
            out.append(("added", f["tool"], f["args"], "new call"))
    return out


_MISSING = object()


def _delta(e, f):
    """Field-level change for dict results, else a before -> after summary."""
    r1, r2 = e.get("result"), f.get("result")
    if isinstance(r1, dict) and isinstance(r2, dict) and not e.get("error") and not f.get("error"):
        parts = []
        for k in sorted(set(r1) | set(r2)):
            v1, v2 = r1.get(k, _MISSING), r2.get(k, _MISSING)
            if v1 is _MISSING or v2 is _MISSING or _canon(v1) != _canon(v2):
                fmt = lambda v: "(missing)" if v is _MISSING else _canon(v)
                parts.append("%s: %s -> %s" % (k, fmt(v1), fmt(v2)))
        return "; ".join(parts)
    return _summ(e) + "  ->  " + _summ(f)


def _summ(e, width=48):
    s = ("error " + e["error"]) if e.get("error") else _canon(e.get("result"))
    return s if len(s) <= width else s[: width - 3] + "..."
