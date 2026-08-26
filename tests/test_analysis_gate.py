import unittest

from ours.agent.analysis_gate import claims_entity_counting, contradicts_analysis
from ours.agent.config import get_agent_config

# Verbatim counting_unit strings from the stage-one runs, so the thresholds are
# tested against what the model actually writes rather than invented phrasing.
# Source: trace/qa_stage1_qa_run{1,2}/transcripts.jsonl
REAL_ENTITY_CLAIMS = [
    "players (entities), because the phrase 'at least once' refers to a "
    "player-level condition rather than raw records",
    "Patients, counted as unique individuals rather than raw test rows.",
    "Patients (unique people), not laboratory rows; the phrase 'at least one "
    "record' means a patient should count once",
    "Entities (cards), not table rows; each card should be counted once if it "
    "is banned and has a white border.",
]
REAL_NON_CLAIMS = [
    # Says rows outright.
    "cards; identical card records are counted as separate rows unless the "
    "question’s phrasing says otherwise",
    # Hedged: the model withdraws the claim in the same sentence.
    "patients/entities rather than raw rows, though the wording could be read "
    "as lab records if a patient has multiple measurements",
    "patients, not raw rows, if the question is interpreted literally; however "
    "the hint’s calculation language refers to summing matching records",
    # Bare noun, no granularity stated.
    "cards",
]

ROW_COUNTING_SQL = "SELECT COUNT(T1.ID) FROM Patient AS T1 JOIN Laboratory AS T2 ON T1.ID = T2.ID"
DISTINCT_SQL = "SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 JOIN Laboratory AS T2 ON T1.ID = T2.ID"


def _analysis(counting_unit: str) -> dict:
    return {"counting_unit": counting_unit}


class ClaimDetectionTests(unittest.TestCase):
    def test_recognises_real_entity_claims(self):
        for text in REAL_ENTITY_CLAIMS:
            self.assertTrue(claims_entity_counting(_analysis(text)), text[:40])

    def test_ignores_row_claims_hedges_and_bare_nouns(self):
        for text in REAL_NON_CLAIMS:
            self.assertFalse(claims_entity_counting(_analysis(text)), text[:40])

    def test_missing_or_empty_analysis_claims_nothing(self):
        self.assertFalse(claims_entity_counting(None))
        self.assertFalse(claims_entity_counting({}))
        self.assertFalse(claims_entity_counting(_analysis("   ")))


class GateTests(unittest.TestCase):
    def test_blocks_row_counting_after_an_entity_claim(self):
        reason = contradicts_analysis(ROW_COUNTING_SQL, _analysis(REAL_ENTITY_CLAIMS[1]))
        self.assertIsNotNone(reason)
        self.assertIn("COUNT(DISTINCT", reason)

    def test_allows_distinct_counting(self):
        self.assertIsNone(
            contradicts_analysis(DISTINCT_SQL, _analysis(REAL_ENTITY_CLAIMS[1]))
        )

    def test_silent_when_the_analysis_made_no_clear_claim(self):
        for text in REAL_NON_CLAIMS:
            self.assertIsNone(contradicts_analysis(ROW_COUNTING_SQL, _analysis(text)), text[:40])

    def test_silent_when_the_query_does_not_count(self):
        # No count at stake, so entity-vs-row does not apply.
        sql = "SELECT name FROM Patient ORDER BY Birthday ASC LIMIT 1"
        self.assertIsNone(contradicts_analysis(sql, _analysis(REAL_ENTITY_CLAIMS[0])))

    def test_silent_without_an_analysis(self):
        self.assertIsNone(contradicts_analysis(ROW_COUNTING_SQL, None))

    def test_reason_quotes_the_models_own_words(self):
        # The message has to be traceable to what the model committed to,
        # otherwise it reads as the harness inventing a requirement.
        claim = REAL_ENTITY_CLAIMS[3]
        reason = contradicts_analysis(ROW_COUNTING_SQL, _analysis(claim))
        self.assertIn(claim[:25], reason)


class ProfileTests(unittest.TestCase):
    def test_gated_profile_differs_from_ungated_only_in_the_mode(self):
        plain = get_agent_config("e3-c-recursive-db-qa").to_manifest()
        gated = get_agent_config("e3-c-recursive-db-qa-gated").to_manifest()
        differing = {k for k in set(plain) | set(gated) if plain.get(k) != gated.get(k)}
        self.assertEqual(
            differing,
            {"profile", "experiment_variant", "planner_mode", "question_analysis"},
        )

    def test_gated_profile_is_marked_gated_in_its_manifest(self):
        gated = get_agent_config("e3-c-recursive-db-qa-gated").to_manifest()
        self.assertTrue(gated["question_analysis"]["gated"])
        plain = get_agent_config("e3-c-recursive-db-qa").to_manifest()
        self.assertFalse(plain["question_analysis"]["gated"])


if __name__ == "__main__":
    unittest.main()
