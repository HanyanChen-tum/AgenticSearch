import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import sqlglot

from ours.agent.config import get_agent_config
from ours.agent.sql_conventions import (
    KNOWN_VERSIONS,
    VERSION,
    VERSION_TIES,
    SqlConventionRewriter,
    get_sql_convention_rewriter,
)


def _rewrite(sql: str) -> str:
    return get_sql_convention_rewriter(VERSION_TIES).rewrite(sql).sql


def _applied(sql: str) -> tuple[str, ...]:
    return get_sql_convention_rewriter(VERSION_TIES).rewrite(sql).applied


class KeepTiesRewriteTests(unittest.TestCase):
    def test_fires_on_plain_superlative(self):
        out = _rewrite("SELECT name FROM player ORDER BY rating DESC LIMIT 1")
        self.assertIn("keep_ties", _applied("SELECT name FROM player ORDER BY rating DESC LIMIT 1"))
        self.assertNotIn("LIMIT", out.upper())
        self.assertIn("MAX", out.upper())

    def test_ascending_uses_min(self):
        out = _rewrite("SELECT name FROM player ORDER BY born ASC LIMIT 1")
        self.assertIn("MIN", out.upper())
        self.assertNotIn("MAX", out.upper())

    def test_bare_order_by_defaults_to_ascending(self):
        # SQLite's default direction is ASC, so the extremum is the minimum.
        out = _rewrite("SELECT name FROM player ORDER BY born LIMIT 1")
        self.assertIn("MIN", out.upper())

    def test_resolves_projection_alias(self):
        # bird_12's shape: the sort key names a projected alias, which does not
        # exist inside the subquery the rewrite builds.
        sql = ("SELECT (1.0 * a) / b AS rate FROM frpm "
               "WHERE b > 0 ORDER BY rate DESC LIMIT 1")
        out = _rewrite(sql)
        self.assertNotIn("= (SELECT MAX(k) FROM (SELECT rate AS k", out)
        self.assertIn("1.0 * a", out)

    def test_grouped_key_goes_to_having_not_where(self):
        sql = ("SELECT league, COUNT(*) FROM match GROUP BY league "
               "ORDER BY COUNT(*) DESC LIMIT 1")
        out = _rewrite(sql).upper()
        self.assertIn("HAVING", out)
        self.assertNotIn("WHERE", out)

    def test_existing_where_is_preserved(self):
        out = _rewrite("SELECT name FROM player WHERE country = 'ES' ORDER BY rating DESC LIMIT 1")
        self.assertIn("country", out)
        self.assertIn("MAX", out.upper())

    def test_declines_multi_key_order_by(self):
        # A second sort key means the query already breaks ties deliberately.
        sql = "SELECT id FROM client ORDER BY birth ASC, salary ASC LIMIT 1"
        self.assertEqual(_applied(sql), ("",)[:0])

    def test_declines_limit_other_than_one(self):
        self.assertEqual(_applied("SELECT name FROM player ORDER BY rating DESC LIMIT 5"), ())

    def test_declines_without_limit(self):
        self.assertEqual(_applied("SELECT name FROM player ORDER BY rating DESC"), ())

    def test_declines_with_offset(self):
        sql = "SELECT name FROM player ORDER BY rating DESC LIMIT 1 OFFSET 3"
        self.assertEqual(_applied(sql), ())

    def test_unparseable_sql_is_left_alone(self):
        result = get_sql_convention_rewriter(VERSION_TIES).rewrite("SELECT FROM WHERE ((")
        self.assertTrue(result.parse_failed or not result.changed)

    def test_rewrite_is_valid_sql(self):
        out = _rewrite("SELECT name FROM player WHERE country = 'ES' ORDER BY rating DESC LIMIT 1")
        sqlglot.parse_one(out, dialect="sqlite")


class KeepTiesSemanticsTests(unittest.TestCase):
    """The point of the rule: same answer when unique, all rows when tied."""

    def _db(self, directory: str, rows) -> Path:
        path = Path(directory) / "t.sqlite"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE player (name TEXT, rating INT)")
            connection.executemany("INSERT INTO player VALUES (?, ?)", rows)
            connection.commit()
        return path

    def _run(self, path: Path, sql: str):
        with closing(sqlite3.connect(path)) as connection:
            return {tuple(r) for r in connection.execute(sql).fetchall()}

    def test_unique_extremum_is_unchanged(self):
        original = "SELECT name FROM player ORDER BY rating DESC LIMIT 1"
        with tempfile.TemporaryDirectory() as directory:
            path = self._db(directory, [("a", 9), ("b", 5), ("c", 1)])
            self.assertEqual(self._run(path, original), self._run(path, _rewrite(original)))

    def test_tie_keeps_every_row(self):
        original = "SELECT name FROM player ORDER BY rating DESC LIMIT 1"
        with tempfile.TemporaryDirectory() as directory:
            path = self._db(directory, [("a", 9), ("b", 9), ("c", 1)])
            self.assertEqual(len(self._run(path, original)), 1)
            self.assertEqual(self._run(path, _rewrite(original)), {("a",), ("b",)})


class ArtifactWiringTests(unittest.TestCase):
    def test_v1_leaves_keep_ties_off(self):
        # Existing profiles must behave exactly as before.
        self.assertNotIn("keep_ties", get_sql_convention_rewriter(VERSION).enabled_conventions)

    def test_v2_enables_keep_ties(self):
        self.assertIn("keep_ties", get_sql_convention_rewriter(VERSION_TIES).enabled_conventions)

    def test_both_versions_are_known(self):
        self.assertEqual(KNOWN_VERSIONS, {VERSION, VERSION_TIES})

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            get_sql_convention_rewriter("train-conventions-v99")

    def test_inverse_rules_cannot_both_be_enabled(self):
        # keep_ties and superlative_order_limit are exact inverses; enabling both
        # would make the output depend on rule ordering.
        payload = json.loads(
            (Path(__file__).resolve().parents[1] / "data" / "processed"
             / "sql_conventions_v2_ties.json").read_text(encoding="utf-8")
        )
        payload["conventions"]["superlative_order_limit"]["enabled"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                SqlConventionRewriter(path)


class ProfileTests(unittest.TestCase):
    def test_keepties_profile_differs_from_base_in_one_field(self):
        base = get_agent_config("e3-c-recursive-db").to_manifest()
        ties = get_agent_config("e3-c-recursive-db-keepties").to_manifest()
        differing = {
            key for key in set(base) | set(ties)
            if base.get(key) != ties.get(key)
        }
        self.assertEqual(differing, {"profile", "experiment_variant", "sql_convention_mode"})

    def test_keepties_profile_uses_the_v2_artifact(self):
        config = get_agent_config("e3-c-recursive-db-keepties")
        self.assertEqual(config.sql_convention_mode, VERSION_TIES)


if __name__ == "__main__":
    unittest.main()
