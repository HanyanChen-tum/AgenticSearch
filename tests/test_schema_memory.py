from ours.metadata import DatabaseMetadata, TableMetadata
from ours.schema_memory import SchemaMemory


def make_metadata() -> DatabaseMetadata:
    return DatabaseMetadata(
        db_path="example.sqlite",
        tables=[
            TableMetadata(
                name="customers",
                row_count=2,
                columns=[
                    {
                        "name": "customer_id",
                        "type": "INTEGER",
                        "not_null": True,
                        "primary_key": True,
                    },
                    {
                        "name": "currency",
                        "type": "TEXT",
                        "not_null": False,
                        "primary_key": False,
                    },
                ],
                foreign_keys=[],
            ),
            TableMetadata(
                name="orders",
                row_count=3,
                columns=[
                    {
                        "name": "order_id",
                        "type": "INTEGER",
                        "not_null": True,
                        "primary_key": True,
                    },
                    {
                        "name": "amount",
                        "type": "REAL",
                        "not_null": False,
                        "primary_key": False,
                    },
                ],
                foreign_keys=[],
            ),
        ],
    )


def test_initial_retrieval_is_bounded_and_question_relevant():
    memory = SchemaMemory(make_metadata())

    results = memory.search("Which customer currency is used?", top_k=2, source="initial")

    assert len(results) == 2
    assert results[0]["table"] == "customers"
    assert results[0]["column"] == "currency"
    assert memory.snapshot()["selected_column_count"] == 2


def test_memory_merges_recursive_columns_without_duplicates():
    memory = SchemaMemory(make_metadata())
    memory.search("currency", top_k=1, source="initial")
    memory.merge_columns(
        {"orders": ["amount", "order_id"], "customers": ["currency"]},
        source="recursive",
    )

    snapshot = memory.snapshot()
    assert snapshot["selected_table_count"] == 2
    assert snapshot["selected_column_count"] == 3
    currency = next(
        item for item in snapshot["columns"] if item["column"] == "currency"
    )
    assert currency["sources"] == ["initial", "recursive"]
