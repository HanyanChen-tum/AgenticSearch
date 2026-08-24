import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from shared.timeout_recovery import execute_sql_with_recovery


class TimeoutRecoveryTests(unittest.TestCase):
    def _build_unindexed_db(self, path: Path, n_a: int = 3000, n_b: int = 300000) -> None:
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE a (id INTEGER)")
            conn.execute("CREATE TABLE b (a_id INTEGER, val INTEGER)")
            conn.executemany("INSERT INTO a VALUES (?)", [(i,) for i in range(n_a)])
            conn.executemany(
                "INSERT INTO b VALUES (?, ?)", [(i % n_a, i * 2) for i in range(n_b)]
            )
            conn.commit()

    def test_recovers_a_correct_answer_after_the_first_attempt_times_out(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            self._build_unindexed_db(path)
            # A correlated EXISTS against an unindexed table forces a full
            # scan of b per row of a, same shape as the bird_1148 case this
            # module exists to fix -- a plain JOIN can be too fast to
            # reliably time out even unindexed on a small synthetic table.
            sql = (
                "SELECT COUNT(*) FROM a AS t1 WHERE EXISTS "
                "(SELECT 1 FROM b AS t2 WHERE t2.a_id = t1.id AND t2.val > 0)"
            )

            baseline = execute_sql_with_recovery(
                path, sql, read_only=True, timeout_seconds=30.0,
            )
            self.assertIsNone(baseline["error"])

            result = execute_sql_with_recovery(
                path, sql, read_only=True,
                timeout_seconds=0.01, recovery_timeout_seconds=30.0,
            )

        self.assertIsNone(result["error"])
        self.assertEqual(result["answer"], baseline["answer"])
        self.assertTrue(result["recovered_via_index"])

    def test_does_not_mark_recovery_when_the_first_attempt_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("CREATE TABLE items (value INTEGER)")
                conn.execute("INSERT INTO items VALUES (7)")
                conn.commit()

            result = execute_sql_with_recovery(
                path, "SELECT value FROM items", read_only=True, timeout_seconds=5.0,
            )

        self.assertEqual(result, {"answer": [[7]], "error": None, "recovered_via_index": False})

    def test_leaves_a_genuine_non_timeout_error_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("CREATE TABLE items (value INTEGER)")
                conn.commit()

            result = execute_sql_with_recovery(
                path, "SELECT * FROM does_not_exist", read_only=True, timeout_seconds=5.0,
            )

        self.assertFalse(result["recovered_via_index"])
        self.assertIn("no such table", result["error"])

    def test_original_db_file_is_never_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            self._build_unindexed_db(path)
            original_bytes = path.read_bytes()

            sql = (
                "SELECT COUNT(*) FROM a AS t1 WHERE EXISTS "
                "(SELECT 1 FROM b AS t2 WHERE t2.a_id = t1.id AND t2.val > 0)"
            )
            execute_sql_with_recovery(
                path, sql, read_only=True,
                timeout_seconds=0.01, recovery_timeout_seconds=10.0,
            )

            self.assertEqual(path.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()
