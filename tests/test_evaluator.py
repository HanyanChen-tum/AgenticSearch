from __future__ import annotations

import unittest

from scripts.evaluate_results import summarize_results
from shared.evaluator import (
    build_evaluation_fields,
    component_sql_match,
    exact_sql_match,
)


class EvaluatorTest(unittest.TestCase):
    def test_exact_match_ignores_case_whitespace_and_semicolon(self) -> None:
        self.assertTrue(
            exact_sql_match(
                "SELECT COUNT(*) FROM employees;",
                " select count(*) from employees ",
            )
        )

    def test_component_match_compares_tables_joins_and_aggregations(self) -> None:
        predicted = (
            "SELECT d.name, AVG(e.salary) "
            "FROM departments d JOIN employees e ON d.id = e.department_id "
            "GROUP BY d.name"
        )
        gold = (
            "SELECT d.name, AVG(e.salary) "
            "FROM departments d JOIN employees e ON d.id = e.department_id "
            "GROUP BY d.name"
        )

        self.assertEqual(
            component_sql_match(predicted, gold),
            {
                "tables": True,
                "columns": True,
                "joins": True,
                "aggregations": True,
            },
        )

    def test_failure_type_prioritizes_invalid_sql(self) -> None:
        fields = build_evaluation_fields(
            "SELECT missing FROM employees",
            "SELECT COUNT(*) FROM employees",
            predicted_error="no such column: missing",
            gold_error=None,
            execution_correct=False,
        )

        self.assertEqual(fields["failure_type"], "invalid_sql")
        self.assertFalse(fields["sql_valid"])

    def test_failure_type_detects_wrong_table(self) -> None:
        fields = build_evaluation_fields(
            "SELECT COUNT(*) FROM departments",
            "SELECT COUNT(*) FROM employees",
            predicted_error=None,
            gold_error=None,
            execution_correct=False,
        )

        self.assertEqual(fields["failure_type"], "wrong_table")

    def test_failure_type_detects_wrong_join(self) -> None:
        fields = build_evaluation_fields(
            (
                "SELECT d.name FROM departments d "
                "JOIN employees e ON d.name = e.department_id"
            ),
            (
                "SELECT d.name FROM departments d "
                "JOIN employees e ON d.id = e.department_id"
            ),
            predicted_error=None,
            gold_error=None,
            execution_correct=False,
        )

        self.assertEqual(fields["failure_type"], "wrong_join")

    def test_failure_type_detects_wrong_aggregation(self) -> None:
        fields = build_evaluation_fields(
            "SELECT COUNT(salary) FROM employees",
            "SELECT AVG(salary) FROM employees",
            predicted_error=None,
            gold_error=None,
            execution_correct=False,
        )

        self.assertEqual(fields["failure_type"], "wrong_aggregation")

    def test_summary_computes_new_metrics_for_legacy_rows(self) -> None:
        summary = summarize_results(
            "method",
            [
                {
                    "correct": True,
                    "predicted_sql": "SELECT COUNT(*) FROM employees",
                    "gold_sql": "SELECT COUNT(*) FROM employees",
                    "error": None,
                    "latency_seconds": 1.0,
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "tool_calls": 0,
                },
                {
                    "correct": False,
                    "predicted_sql": "SELECT COUNT(*) FROM departments",
                    "gold_sql": "SELECT COUNT(*) FROM employees",
                    "error": None,
                    "latency_seconds": 3.0,
                    "input_tokens": 11,
                    "output_tokens": 3,
                    "actions_used": 4,
                },
            ],
        )

        self.assertEqual(summary["execution_accuracy"], 0.5)
        self.assertEqual(summary["sql_valid_rate"], 1.0)
        self.assertEqual(summary["error_rate"], 0.0)
        self.assertEqual(summary["exact_match_accuracy"], 0.5)
        self.assertEqual(summary["component_accuracy"]["tables"], 0.5)
        self.assertEqual(summary["failure_type_counts"], {"wrong_table": 1})
        self.assertEqual(summary["total_tool_calls"], 4)
        self.assertEqual(summary["avg_tool_calls"], 2.0)


if __name__ == "__main__":
    unittest.main()
