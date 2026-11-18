import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from toolcassette import Cassette, CassetteMiss, load, diff, call_key  # noqa: E402
from toolcassette.cli import main  # noqa: E402


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.p = os.path.join(self.d, "c.jsonl")
        self.calls = 0

    def tools(self, c, bump=0):
        @c.tool
        def add(a, b):
            self.calls += 1
            return a + b + bump

        @c.tool(name="boom")
        def explode(x):
            self.calls += 1
            raise ValueError("bad x %s" % x)
        return add, explode

    def test_key_is_order_independent(self):
        self.assertEqual(call_key("t", {"a": 1, "b": 2}), call_key("t", {"b": 2, "a": 1}))
        self.assertNotEqual(call_key("t", {"a": 1}), call_key("u", {"a": 1}))

    def test_record_then_replay_skips_real_tool(self):
        add, _ = self.tools(Cassette(self.p, "record"))
        self.assertEqual(add(a=1, b=2), 3)
        self.assertEqual(self.calls, 1)
        c = Cassette(self.p, "replay")
        add, _ = self.tools(c, bump=100)
        self.assertEqual(add(a=1, b=2), 3)
        self.assertEqual(self.calls, 1)
        self.assertEqual(c.stats["replayed"], 1)

    def test_replay_miss_raises(self):
        self.tools(Cassette(self.p, "record"))[0](a=1, b=2)
        add, _ = self.tools(Cassette(self.p, "replay"))
        with self.assertRaises(CassetteMiss):
            add(a=5, b=5)

    def test_errors_are_recorded_and_replayed(self):
        _, boom = self.tools(Cassette(self.p, "record"))
        with self.assertRaises(ValueError):
            boom(x=1)
        _, boom = self.tools(Cassette(self.p, "replay"))
        with self.assertRaisesRegex(RuntimeError, "ValueError: bad x 1"):
            boom(x=1)
        self.assertEqual(self.calls, 1)

    def test_auto_records_only_new_calls(self):
        self.tools(Cassette(self.p, "record"))[0](a=1, b=2)
        c = Cassette(self.p, "auto")
        add, _ = self.tools(c)
        add(a=1, b=2)
        add(a=3, b=4)
        self.assertEqual(c.stats, {"recorded": 1, "replayed": 1, "missed": 0})
        self.assertEqual(len(load(self.p)), 2)

    def test_repeated_calls_replay_in_order(self):
        n = {"i": 0}
        c = Cassette(self.p, "record")

        @c.tool
        def tick():
            n["i"] += 1
            return n["i"]
        tick(); tick()
        c = Cassette(self.p, "replay")
        tick = c.tool(lambda: 0, name="tick")
        self.assertEqual([tick(), tick(), tick()], [1, 2, 2])

    def test_record_overwrites(self):
        self.tools(Cassette(self.p, "record"))[0](a=1, b=2)
        self.tools(Cassette(self.p, "record"))[0](a=2, b=2)
        self.assertEqual([e["args"] for e in load(self.p)], [{"a": 2, "b": 2}])

    def test_env_mode_and_bad_mode(self):
        os.environ["TOOL_CASSETTE"] = "replay"
        try:
            self.assertEqual(Cassette(self.p).mode, "replay")
        finally:
            del os.environ["TOOL_CASSETTE"]
        with self.assertRaises(ValueError):
            Cassette(self.p, "live")

    def test_diff_kinds(self):
        p2 = os.path.join(self.d, "c2.jsonl")
        a, _ = self.tools(Cassette(self.p, "record"))
        a(a=1, b=1); a(a=2, b=2)
        a, _ = self.tools(Cassette(p2, "record"), bump=1)
        a(a=1, b=1); a(a=3, b=3)
        kinds = sorted(k for k, *_ in diff(load(self.p), load(p2)))
        self.assertEqual(kinds, ["added", "changed", "removed"])
        self.assertEqual(diff(load(self.p), load(self.p)), [])

    def test_cli_exit_codes(self):
        self.tools(Cassette(self.p, "record"))[0](a=1, b=2)
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["show", self.p]), 0)
            self.assertEqual(main(["diff", self.p, self.p]), 0)
        with open(os.path.join(self.d, "bad.jsonl"), "w") as f:
            f.write("{nope\n")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["show", os.path.join(self.d, "bad.jsonl")]), 2)


if __name__ == "__main__":
    unittest.main()
