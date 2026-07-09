import sqlite3

from ours.db_environment import DBEnvironment


def test_db_environment_records_schema_and_sql_calls(tmp_path):
    db_path = tmp_path / "example.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("INSERT INTO items(name) VALUES ('a')")

    db = DBEnvironment(db_path)
    assert db.get_tables() == ["items"]
    db.get_schema("items")
    db.sample_rows("items", limit=1)
    db.execute("SELECT COUNT(*) FROM items")

    stats = db.stats()
    assert stats["tool_calls"] == 4
    assert stats["retrieval_calls"] == 2
    assert stats["sql_execution_calls"] == 1
    assert stats["inspected_tables"] == ["items"]
    assert stats["inspected_columns"]["items"] == ["id", "name"]
