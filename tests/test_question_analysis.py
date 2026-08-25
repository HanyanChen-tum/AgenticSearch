import json
import unittest

from ours.agent.config import AgentConfig, get_agent_config
from ours.agent.question_analysis import (
    QUESTION_ANALYSIS_MODE,
    REQUIRED_FIELDS,
    parse_analysis,
    protocol_manifest,
    retry_instruction,
)

GOOD = {
    "answer_shape": "one column: the patient ID",
    "counting_unit": "entities (patients), not laboratory rows",
    "stated_conditions": ["diagnosed with SLE", "normal hemoglobin"],
    "unit_and_scale": "a count, no percentage",
    "ambiguities": [],
}


def _block(payload) -> str:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return f"Here is my reading.\n```question-analysis\n{body}\n```"


class ParseTests(unittest.TestCase):
    def test_accepts_a_complete_block(self):
        analysis, errors = parse_analysis(_block(GOOD))
        self.assertEqual(errors, [])
        self.assertEqual(analysis, GOOD)

    def test_rejects_a_missing_block(self):
        analysis, errors = parse_analysis("I'll just write the SQL directly.")
        self.assertIsNone(analysis)
        self.assertTrue(errors)

    def test_rejects_invalid_json(self):
        analysis, errors = parse_analysis(_block("{not json"))
        self.assertIsNone(analysis)
        self.assertIn("not valid JSON", errors[0])

    def test_names_every_missing_field(self):
        partial = {"answer_shape": "one column"}
        _, errors = parse_analysis(_block(partial))
        joined = " ".join(errors)
        for name in REQUIRED_FIELDS:
            if name != "answer_shape":
                self.assertIn(name, joined)

    def test_list_fields_must_be_lists(self):
        bad = {**GOOD, "stated_conditions": "diagnosed with SLE"}
        _, errors = parse_analysis(_block(bad))
        self.assertTrue(any("stated_conditions" in e for e in errors))

    def test_empty_lists_are_allowed(self):
        analysis, errors = parse_analysis(_block({**GOOD, "stated_conditions": []}))
        self.assertEqual(errors, [])
        self.assertEqual(analysis["stated_conditions"], [])

    def test_string_fields_must_be_non_empty(self):
        _, errors = parse_analysis(_block({**GOOD, "counting_unit": "   "}))
        self.assertTrue(any("counting_unit" in e for e in errors))

    def test_extra_keys_are_dropped_not_rejected(self):
        # Refusing extra keys would make the model retry over something that
        # cannot affect the answer.
        analysis, errors = parse_analysis(_block({**GOOD, "my_plan": "join a to b"}))
        self.assertEqual(errors, [])
        self.assertNotIn("my_plan", analysis)

    def test_retry_instruction_lists_the_fields_and_forbids_sql(self):
        text = retry_instruction(["missing required fields: counting_unit"])
        for name in REQUIRED_FIELDS:
            self.assertIn(name, text)
        self.assertIn("Do not write any SQL", text)


class ManifestTests(unittest.TestCase):
    def test_manifest_records_the_stage_and_fields(self):
        manifest = protocol_manifest()
        self.assertEqual(manifest["mode"], QUESTION_ANALYSIS_MODE)
        self.assertEqual(manifest["stage"], "before-first-query")
        self.assertEqual(sorted(REQUIRED_FIELDS), manifest["required_fields"])

    def test_exactly_five_fields_and_none_about_sql(self):
        # The whole point of this arm versus E4-A: five fields, about the
        # question. E4-A required 20 including joins/filters/having and measured
        # -3.05pp while making its own target class worse.
        self.assertEqual(len(REQUIRED_FIELDS), 5)
        forbidden = {"join", "joins", "filters", "group_by", "having", "tables", "sql"}
        self.assertEqual(forbidden & set(REQUIRED_FIELDS), set())


class ProfileTests(unittest.TestCase):
    def test_qa_profile_differs_from_base_only_in_the_paired_fields(self):
        base = get_agent_config("e3-c-recursive-db").to_manifest()
        qa = get_agent_config("e3-c-recursive-db-qa").to_manifest()
        differing = {k for k in set(base) | set(qa) if base.get(k) != qa.get(k)}
        self.assertEqual(
            differing,
            {"profile", "experiment_variant", "planner_mode", "prompt_profile",
             "prompt", "question_analysis"},
        )

    def test_qa_profile_keeps_recursion_so_only_one_behaviour_changes(self):
        base = get_agent_config("e3-c-recursive-db")
        qa = get_agent_config("e3-c-recursive-db-qa")
        self.assertEqual(qa.recursion_mode, base.recursion_mode)
        self.assertEqual(qa.sql_convention_mode, base.sql_convention_mode)

    def test_mode_and_prompt_are_enforced_as_a_pair(self):
        with self.assertRaises(ValueError):
            AgentConfig(
                profile="x", experiment_variant="x",
                prompt_profile="conventions-recursive-v1",
                use_db_hints=False, verified_final=False, capability_gate=True,
                planner_mode=QUESTION_ANALYSIS_MODE,
            )


if __name__ == "__main__":
    unittest.main()
