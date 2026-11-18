"""Demo: record a mock agent's tool calls, replay them offline, then catch API drift.

Everything here is local and fake: the "APIs" are Python functions that sleep to act slow.
"""
import os
import subprocess
import sys
import time

from toolcassette import Cassette, CassetteMiss

HERE = os.path.dirname(os.path.abspath(__file__))
EX = os.path.join(HERE, "examples")


def make_tools(cassette, api_version=1):
    @cassette.tool
    def search_docs(query):
        time.sleep(0.25)
        return [{"id": "kb-12", "title": "Refund policy"}, {"id": "kb-40", "title": "Plan limits"}]

    @cassette.tool
    def get_order(order_id):
        time.sleep(0.35)
        order = {"id": order_id, "status": "shipped", "total": 49.0}
        if api_version == 2:  # upstream renamed a field and changed a value
            order = {"id": order_id, "state": "delivered", "total": 49.0}
        return order

    @cassette.tool
    def refund_quote(order_id, reason):
        time.sleep(0.30)
        return {"order_id": order_id, "refundable": True, "amount": 49.0}

    return search_docs, get_order, refund_quote


def agent(tools, order_id="A-1001"):
    """A scripted 'agent': the same plan a model would make, minus the model."""
    search_docs, get_order, refund_quote = tools
    search_docs(query="refund policy")
    order = get_order(order_id=order_id)
    quote = refund_quote(order_id=order_id, reason="damaged")
    return "order %s: %s, refund $%.2f" % (order_id, order.get("status", order.get("state")), quote["amount"])


def run(label, mode, path, **kw):
    c = Cassette(path, mode=mode)
    t0 = time.perf_counter()
    answer = agent(make_tools(c, kw.pop("api_version", 1)), **kw)
    ms = (time.perf_counter() - t0) * 1000
    print("$ TOOL_CASSETTE=%s python agent.py   # %s" % (mode, label))
    print("  %s" % answer)
    print("  %d recorded, %d replayed, %.1f ms" % (c.stats["recorded"], c.stats["replayed"], ms))
    print()


def cli(*args):
    args = [os.path.relpath(a, HERE) if os.path.isabs(a) else a for a in args]
    print("$ tool-cassette " + " ".join(args))
    r = subprocess.run([sys.executable, "-m", "toolcassette"] + list(args),
                       cwd=HERE, capture_output=True, text=True)
    print(r.stdout.rstrip())
    print("(exit code %d)" % r.returncode)
    print()


if __name__ == "__main__":
    os.makedirs(EX, exist_ok=True)
    v1 = os.path.join(EX, "support_v1.jsonl")
    v2 = os.path.join(EX, "support_v2.jsonl")
    run("hits the live tools once", "record", v1)
    run("offline, no network, same answer", "replay", v1)
    cli("show", v1)
    try:
        c = Cassette(v1, mode="replay")
        agent(make_tools(c), order_id="B-2002")
    except CassetteMiss as e:
        print("$ TOOL_CASSETTE=replay python agent.py --order B-2002   # new path")
        print("  CassetteMiss: " + e.args[0].split(";")[0].replace(EX + os.sep, "examples/"))
        print()
    run("a week later, re-record against the 'live' API", "record", v2, api_version=2)
    cli("diff", v1, v2)
