import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from shared.sql_executor import execute_sql


class SQLExecutorTests(unittest.TestCase):
    def test_execute_sql_times_out_runaway_query(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("CREATE TABLE items (value INTEGER)")
                connection.commit()

            started = time.monotonic()
            result = execute_sql(
                path,
                """
                WITH RECURSIVE counter(value) AS (
                    VALUES(0)
                    UNION ALL
                    SELECT value + 1 FROM counter WHERE value < 100000000
                )
                SELECT SUM(value) FROM counter
                """,
                read_only=True,
                timeout_seconds=0.01,
            )

        self.assertIsNone(result["answer"])
        self.assertIn("timed out", result["error"])
        self.assertLess(time.monotonic() - started, 2)

    def test_execute_sql_still_returns_normal_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("CREATE TABLE items (value INTEGER)")
                connection.execute("INSERT INTO items VALUES (7)")
                connection.commit()

            result = execute_sql(
                path,
                "SELECT value FROM items",
                read_only=True,
                timeout_seconds=1,
            )

        self.assertEqual(result, {"answer": [[7]], "error": None})


if __name__ == "__main__":
    unittest.main()
