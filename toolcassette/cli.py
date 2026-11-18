"""tool-cassette CLI: show and diff cassettes."""
import argparse
import json
import sys

from .core import load, diff, _canon


def _args(a, width=40):
    s = _canon(a)
    return s if len(s) <= width else s[: width - 3] + "..."


def cmd_show(ns):
    entries = load(ns.cassette)
    total = sum(e.get("ms") or 0 for e in entries)
    tools = {}
    for e in entries:
        tools[e["tool"]] = tools.get(e["tool"], 0) + 1
    print("%s: %d calls, %d tools, replay skips %.0f ms of live tool time"
          % (ns.cassette, len(entries), len(tools), total))
    for e in entries:
        flag = "ERR " if e.get("error") else "    "
        print("  %s%-14s %-42s %7.1f ms" % (flag, e["tool"], _args(e["args"]), e.get("ms") or 0))
    return 0


def cmd_diff(ns):
    changes = diff(load(ns.old), load(ns.new))
    if ns.json:
        print(json.dumps([dict(zip(("kind", "tool", "args", "detail"), c)) for c in changes], indent=2))
    elif not changes:
        print("no drift: every tool call returned the same thing")
    else:
        print("%d tool call(s) drifted:" % len(changes))
        for kind, tool, args, detail in changes:
            print("  %-8s %s(%s)  %s" % (kind.upper(), tool, _args(args, 28), detail))
    return 1 if changes else 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="tool-cassette",
                                description="Record an agent's tool calls once, replay them offline.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="list the calls on a cassette")
    s.add_argument("cassette")
    s.set_defaults(fn=cmd_show)
    d = sub.add_parser("diff", help="compare two cassettes; exit 1 if any tool output drifted")
    d.add_argument("old")
    d.add_argument("new")
    d.add_argument("--json", action="store_true")
    d.set_defaults(fn=cmd_diff)
    ns = p.parse_args(argv)
    try:
        return ns.fn(ns)
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
