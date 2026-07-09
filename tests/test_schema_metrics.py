import sqlite3

from shared.schema_metrics import calculate_schema_metrics, extract_gold_schema


def make_database(path):
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE customers(customer_id INTEGER PRIMARY KEY, currency TEXT)"
        )
        connection.execute(
            "CREATE TABLE orders(order_id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL)"
        )


def test_extract_gold_schema_resolves_aliases_and_columns(tmp_path):
    db_path = tmp_path / "example.sqlite"
    make_database(db_path)

    gold = extract_gold_schema(
        """
        SELECT c.currency, SUM(o.amount)
        FROM customers AS c
        JOIN orders AS o ON c.customer_id = o.customer_id
        GROUP BY c.currency
        """,
        db_path,
    )

    assert gold["tables"] == ["customers", "orders"]
    assert {item["table"] + "." + item["column"] for item in gold["columns"]} == {
        "customers.currency",
        "customers.customer_id",
        "orders.customer_id",
        "orders.amount",
    }


def test_calculate_schema_metrics_reports_missing_schema():
    gold = {
        "tables": ["customers", "orders"],
        "columns": [
            {"table": "customers", "column": "customer_id"},
            {"table": "orders", "column": "amount"},
        ],
        "unresolved_columns": [],
    }
    metrics = calculate_schema_metrics(
        gold,
        selected_tables=["customers"],
        selected_columns=[{"table": "customers", "column": "customer_id"}],
    )

    assert metrics["table_recall"] == 0.5
    assert metrics["column_recall"] == 0.5
    assert metrics["strict_schema_recall"] is False
    assert metrics["missing_tables"] == ["orders"]
