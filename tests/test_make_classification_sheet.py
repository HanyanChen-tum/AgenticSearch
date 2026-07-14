import unittest

from scripts.make_classification_sheet import FIELDNAMES, classify_failure


def result(predicted_sql, gold_sql="SELECT value FROM t", **overrides):
    base = {
        "id": "bird_test",
        "predicted_sql": predicted_sql,
        "gold_sql": gold_sql,
        "error": None,
        "termination": "final",
    }
    base.update(overrides)
    return base


def transcript(*messages):
    return {"id": "bird_test", "messages": list(messages)}


class ClassificationTests(unittest.TestCase):
    def test_no_assistant_output_is_runner_failure(self):
        trace = transcript({"role": "user", "content": "QUESTION"})
        classified = classify_failure(result("", termination="error"), trace)
        self.assertEqual(classified["wrong_turn"], "0")
        self.assertEqual(classified["error_class"], "RUNNER_OR_API")

    def test_changed_final_sql_is_unverified(self):
        trace = transcript(
            {"role": "user", "content": "QUESTION"},
            {"role": "assistant", "content": '"""python\nprint(db.execute("SELECT 1"))\n"""'},
            {"role": "user", "content": "{'columns': ['1'], 'rows': [[1]], 'error': None}"},
            {"role": "assistant", "content": 'FINAL("SELECT 2")'},
        )
        # Replace the test-only fence marker with actual markdown fences.
        trace["messages"][1]["content"] = trace["messages"][1]["content"].replace('"""', '```')
        classified = classify_failure(result("SELECT 2"), trace)
        self.assertEqual(classified["wrong_turn"], "2")
        self.assertEqual(classified["error_class"], "UNVERIFIED_FINAL")
        self.assertEqual(classified["control_flow_class"], "UNVERIFIED_FINAL")
        self.assertTrue(classified["semantic_error_class"])
        self.assertTrue(classified["semantic_subcategory"])
        self.assertTrue(classified["sql_change_type"])
        self.assertEqual(
            classified["subcategory"],
            "final_sql_rewritten_after_successful_observation",
        )

    def test_changed_final_after_sql_error_records_last_observation(self):
        trace = transcript(
            {"role": "user", "content": "QUESTION"},
            {"role": "assistant", "content": '```python\nprint(db.execute("SELECT missing FROM t"))\n```'},
            {"role": "user", "content": "{'rows': [], 'error': 'no such column: missing'}"},
            {"role": "assistant", "content": 'FINAL("SELECT value FROM t")'},
        )
        classified = classify_failure(result("SELECT value FROM t"), trace)
        self.assertEqual(classified["error_class"], "UNVERIFIED_FINAL")
        self.assertEqual(classified["subcategory"], "final_sql_changed_after_sql_error")
        self.assertIn("SQL ERROR", classified["notes"])

    def test_changed_final_after_empty_result_records_last_observation(self):
        trace = transcript(
            {"role": "user", "content": "QUESTION"},
            {"role": "assistant", "content": '```python\nprint(db.execute("SELECT value FROM t WHERE 0"))\n```'},
            {"role": "user", "content": "{'rows': [], 'error': None}"},
            {"role": "assistant", "content": 'FINAL("SELECT value FROM t")'},
        )
        classified = classify_failure(result("SELECT value FROM t"), trace)
        self.assertEqual(classified["error_class"], "UNVERIFIED_FINAL")
        self.assertEqual(classified["subcategory"], "final_sql_changed_after_empty_result")

    def test_structured_trace_marks_whether_rewritten_final_replaced_correct_sql(self):
        trace = {
            "id": "bird_test",
            "messages": [{"role": "assistant", "content": 'FINAL("SELECT 2")'}],
            "events": [{
                "turn": 1,
                "tool": "db.execute",
                "arguments": {"sql": "SELECT 1"},
                "result": {"rows": [[1]], "error": None},
            }],
        }
        classified = classify_failure(
            result("SELECT 2", gold_answer=[[1]]),
            trace,
        )
        self.assertEqual(
            classified["subcategory"],
            "final_sql_rewritten_after_correct_observation",
        )

    def test_unknown_column_is_schema_linking(self):
        sql = "SELECT missing FROM t"
        trace = transcript(
            {"role": "user", "content": "QUESTION"},
            {"role": "assistant", "content": f'"""python\nprint(db.execute("{sql}"))\n"""'},
            {"role": "user", "content": "{'rows': [], 'error': 'no such column: missing'}"},
            {"role": "assistant", "content": f'FINAL("{sql}")'},
        )
        trace["messages"][1]["content"] = trace["messages"][1]["content"].replace('"""', '```')
        classified = classify_failure(result(sql), trace)
        self.assertEqual(classified["wrong_turn"], "1")
        self.assertEqual(classified["error_class"], "SCHEMA_LINKING")

    def test_grouping_difference_is_aggregation_reasoning(self):
        predicted = "SELECT customer_id FROM usage ORDER BY consumption ASC LIMIT 1"
        gold = "SELECT customer_id FROM usage GROUP BY customer_id ORDER BY SUM(consumption) ASC LIMIT 1"
        trace = transcript(
            {"role": "user", "content": "QUESTION"},
            {"role": "assistant", "content": f'"""python\nprint(db.execute("{predicted}"))\n"""'},
            {"role": "user", "content": "{'columns': ['customer_id'], 'rows': [[1]], 'error': None}"},
            {"role": "assistant", "content": f'FINAL("{predicted}")'},
        )
        trace["messages"][1]["content"] = trace["messages"][1]["content"].replace('"""', '```')
        classified = classify_failure(result(predicted, gold), trace)
        self.assertEqual(classified["error_class"], "AGGREGATION_REASONING")

    def test_output_column_count_mismatch(self):
        predicted = "SELECT name FROM schools"
        gold = "SELECT name, street FROM schools"
        trace = transcript(
            {"role": "user", "content": "QUESTION"},
            {"role": "assistant", "content": f'"""python\nprint(db.execute("{predicted}"))\n"""'},
            {"role": "user", "content": "{'columns': ['name'], 'rows': [['A']], 'error': None}"},
            {"role": "assistant", "content": f'FINAL("{predicted}")'},
        )
        trace["messages"][1]["content"] = trace["messages"][1]["content"].replace('"""', '```')
        classified = classify_failure(result(predicted, gold), trace)
        self.assertEqual(classified["error_class"], "OUTPUT_CONTRACT")
        self.assertEqual(classified["semantic_error_class"], "OUTPUT_CONTRACT")
        self.assertEqual(classified["control_flow_class"], "")

    def test_csv_schema_keeps_primary_fields_and_adds_parallel_diagnostics(self):
        for field in (
            "error_class",
            "subcategory",
            "control_flow_class",
            "semantic_error_class",
            "semantic_subcategory",
            "sql_change_type",
        ):
            self.assertIn(field, FIELDNAMES)


if __name__ == "__main__":
    unittest.main()
