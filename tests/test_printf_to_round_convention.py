import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import sqlglot

from ours.agent.config import get_agent_config
from ours.agent.sql_conventions import (
    VERSION,
    VERSION_BOTH,
    VERSION_TIES,
    VERSION_TYPES,
    get_sql_convention_rewriter,
)


def _rewrite(sql: str, version: str = VERSION_TYPES) -> str:
    return get_sql_convention_rewriter(version).rewrite(sql).sql


def _applied(sql: str, version: str = VERSION_TYPES) -> tuple[str, ...]:
    return get_sql_convention_rewriter(version).rewrite(sql).applied


class PrintfToRoundTests(unittest.TestCase):
    def test_rewrites_a_lone_float_format(self):
        sql = "SELECT printf('%.5f', 100.0 * SUM(x) / COUNT(y)) FROM bond"
        self.assertIn("printf_to_round", _applied(sql))
        self.assertIn("ROUND", _rewrite(sql).upper())
        self.assertNotIn("PRINTF", _rewrite(sql).upper())

    def test_keeps_the_requested_precision(self):
        self.assertIn(", 3)", _rewrite("SELECT printf('%.3f', x) FROM t"))
        self.assertIn(", 5)", _rewrite("SELECT printf('%.5f', x) FROM t"))

    def test_declines_a_format_carrying_other_text(self):
        # 'Total: %.2f USD' is a string the model meant to build; rewriting it
        # would change the answer rather than its type.
        sql = "SELECT printf('Total: %.2f USD', x) FROM t"
        self.assertEqual(_applied(sql), ())

    def test_declines_non_float_formats(self):
        self.assertEqual(_applied("SELECT printf('%d', x) FROM t"), ())
        self.assertEqual(_applied("SELECT printf('%s', x) FROM t"), ())

    def test_declines_wrong_argument_count(self):
        self.assertEqual(_applied("SELECT printf('%.2f') FROM t"), ())
        self.assertEqual(_applied("SELECT printf('%.2f', a, b) FROM t"), ())

    def test_rewrites_only_the_qualifying_call_when_mixed(self):
        out = _rewrite("SELECT printf('%.2f', a), printf('%d', b) FROM t").upper()
        self.assertIn("ROUND", out)
        self.assertIn("PRINTF", out)

    def test_rewrite_is_valid_sql(self):
        sqlglot.parse_one(_rewrite("SELECT printf('%.4f', a / b) FROM t"), dialect="sqlite")


class PrintfSemanticsTests(unittest.TestCase):
    """The point of the rule: same number, different SQL type."""

    def _db(self, directory: str) -> Path:
        path = Path(directory) / "t.sqlite"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE t (a REAL, b REAL)")
            connection.execute("INSERT INTO t VALUES (1.0, 26.0)")
            connection.commit()
        return path

    def test_printf_returns_text_and_round_returns_a_number(self):
        original = "SELECT printf('%.5f', 100.0 * a / b) FROM t"
        with tempfile.TemporaryDirectory() as directory:
            path = self._db(directory)
            with closing(sqlite3.connect(path)) as connection:
                before = connection.execute(original).fetchone()[0]
                after = connection.execute(_rewrite(original)).fetchone()[0]
        self.assertIsInstance(before, str)
        self.assertIsInstance(after, float)
        self.assertEqual(float(before), after)


class ArtifactVersionTests(unittest.TestCase):
    def test_v1_leaves_both_new_rules_off(self):
        enabled = get_sql_convention_rewriter(VERSION).enabled_conventions
        self.assertNotIn("printf_to_round", enabled)
        self.assertNotIn("keep_ties", enabled)

    def test_v3_enables_only_the_type_rule(self):
        enabled = get_sql_convention_rewriter(VERSION_TYPES).enabled_conventions
        self.assertIn("printf_to_round", enabled)
        self.assertNotIn("keep_ties", enabled)

    def test_v2_enables_only_the_tie_rule(self):
        enabled = get_sql_convention_rewriter(VERSION_TIES).enabled_conventions
        self.assertIn("keep_ties", enabled)
        self.assertNotIn("printf_to_round", enabled)

    def test_v4_enables_both(self):
        enabled = get_sql_convention_rewriter(VERSION_BOTH).enabled_conventions
        self.assertIn("keep_ties", enabled)
        self.assertIn("printf_to_round", enabled)


class ProfileTests(unittest.TestCase):
    def test_each_profile_differs_from_the_base_in_one_field(self):
        base = get_agent_config("e3-c-recursive-db").to_manifest()
        for name in ("e3-c-recursive-db-types", "e3-c-recursive-db-conv2"):
            manifest = get_agent_config(name).to_manifest()
            differing = {
                key for key in set(base) | set(manifest)
                if base.get(key) != manifest.get(key)
            }
            self.assertEqual(
                differing, {"profile", "experiment_variant", "sql_convention_mode"}, name
            )


if __name__ == "__main__":
    unittest.main()
