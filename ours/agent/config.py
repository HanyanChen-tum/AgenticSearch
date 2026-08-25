"""Immutable configuration for DB-agent ablations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

from .prompts import prompt_manifest
from .query_plan import QUERY_PLAN_MODE, protocol_manifest
from .question_analysis import QUESTION_ANALYSIS_MODE
from .question_analysis import protocol_manifest as question_analysis_manifest
from .reasoning_capture import CAPTURE_MODE as REASONING_CAPTURE_MODE
from .sql_conventions import KNOWN_VERSIONS as SQL_CONVENTION_VERSIONS
from .sql_conventions import VERSION as SQL_CONVENTION_VERSION
from .sql_conventions import VERSION_BOTH as SQL_CONVENTION_VERSION_BOTH
from .sql_conventions import VERSION_TIES as SQL_CONVENTION_VERSION_TIES
from .sql_conventions import VERSION_TYPES as SQL_CONVENTION_VERSION_TYPES


AGENT_CONFIG_SCHEMA_VERSION = 1
CAPABILITY_MANIFEST_VERSION = 1


def _manifest_sha256(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class AgentConfig:
    profile: str
    experiment_variant: str
    prompt_profile: str
    use_db_hints: bool
    verified_final: bool
    capability_gate: bool
    few_shot_mode: str = "train-retrieval"
    query_pattern_mode: str = "none"
    offline_metadata_mode: str = "none"
    schema_context_mode: str = "runtime-full"
    context_mode: str = "direct"
    reasoning_mode: str = "none"
    planner_mode: str = "none"
    allowed_db_methods: tuple[str, ...] = ("execute", "sample_values")
    literal_verification_nudge: bool = False
    sql_convention_mode: str = "none"
    # Exposes the RLM recursion primitive without lifting the db-method gate, so
    # recursion can be ablated on its own. Flipping capability_gate instead would
    # change two things at once.
    recursion_mode: str = "none"
    # Routes generation through the Responses API so reasoning summaries are
    # captured alongside the answer they produced. Diagnostic only: it changes
    # the API path, so accuracy is not comparable to Chat Completions runs.
    reasoning_capture: str = "none"
    # Controller executes the exact FINAL SQL itself (once, no extra model
    # turn on the success path) and blocks only on ERROR/EMPTY, telling the
    # model to redesign -- not resubmit -- on a timeout. Distinct from
    # verified_final (rejected in E1: required the *model* to have already
    # run the identical string, which mostly blocked on harmless revisions
    # rather than real problems -- see docs/analysis/analysisDetail/
    # e1_verified_summary.md). See also shared/timeout_recovery.py, which
    # covers the same missing-index timeout class at scoring time; this flag
    # is the corresponding fix on the agent side.
    final_execution_gate: bool = False

    def __post_init__(self) -> None:
        if self.few_shot_mode not in {"train-retrieval", "none"}:
            raise ValueError(f"Unknown few-shot mode: {self.few_shot_mode!r}")
        if self.offline_metadata_mode not in {
            "none", "e3-c-metadata-v1", "e3-c-metadata-v2", "e3-f-schema-v3", "e3-f-schema-v4"
        }:
            raise ValueError(f"Unknown offline metadata mode: {self.offline_metadata_mode!r}")
        if self.schema_context_mode not in {"runtime-full", "offline-retrieval"}:
            raise ValueError(f"Unknown schema context mode: {self.schema_context_mode!r}")
        if self.context_mode not in {"direct", "store-readonly"}:
            raise ValueError(f"Unknown context mode: {self.context_mode!r}")
        if self.sql_convention_mode not in {"none", *SQL_CONVENTION_VERSIONS}:
            raise ValueError(f"Unknown SQL convention mode: {self.sql_convention_mode!r}")
        if self.reasoning_capture not in {"none", REASONING_CAPTURE_MODE}:
            raise ValueError(f"Unknown reasoning capture mode: {self.reasoning_capture!r}")
        if self.recursion_mode not in {"none", "leaf-v1", "leaf-db-v1", "leaf-open-v1"}:
            raise ValueError(f"Unknown recursion mode: {self.recursion_mode!r}")
        # The primitive was present in three earlier profiles but no prompt named
        # it, so it was never invoked. Requiring the prompt that documents it
        # prevents that silent no-op from recurring.
        if self.recursion_mode != "none" and self.prompt_profile not in {
            "basic-recursive-v1", "conventions-recursive-v1", "conventions-recursive-v2-open",
            "conventions-qa-v1"
        }:
            raise ValueError(
                f"recursion_mode={self.recursion_mode!r} requires a prompt profile "
                "that documents recursive_llm"
            )
        if (self.recursion_mode == "leaf-open-v1"
                and self.prompt_profile != "conventions-recursive-v2-open"):
            raise ValueError(
                "leaf-open-v1 requires conventions-recursive-v2-open: the other "
                "recursive prompts tell the model the sub-agent cannot see the "
                "original question, which is no longer true under this mode"
            )
        if self.schema_context_mode == "offline-retrieval" and self.offline_metadata_mode == "none":
            raise ValueError("offline-retrieval requires an offline metadata artifact")
        if self.planner_mode not in {"none", QUERY_PLAN_MODE, QUESTION_ANALYSIS_MODE}:
            raise ValueError(f"Unknown planner mode: {self.planner_mode!r}")
        if self.planner_mode == QUERY_PLAN_MODE and self.prompt_profile != "query-plan-v1":
            raise ValueError("root-query-plan-v1 requires prompt_profile='query-plan-v1'")
        if (self.planner_mode == QUESTION_ANALYSIS_MODE
                and self.prompt_profile != "conventions-qa-v1"):
            raise ValueError(
                "question-analysis-v1 requires prompt_profile='conventions-qa-v1': "
                "the other prompts never ask for the analysis block, so the gate "
                "would reject every first reply"
            )
        if self.final_execution_gate and self.verified_final:
            raise ValueError(
                "final_execution_gate and verified_final are two different FINAL "
                "gates (controller-executed vs model-executed) -- pick one"
            )

    def capability_manifest(self) -> dict:
        manifest = {
            "version": CAPABILITY_MANIFEST_VERSION,
            "gate_enabled": self.capability_gate,
            "allowed_db_methods": list(self.allowed_db_methods),
            "generic_recursive_llm": not self.capability_gate,
            "context_store_readable": self.context_mode == "store-readonly",
            "recursion_exposed": self.recursion_mode != "none",
        }
        return {**manifest, "sha256": _manifest_sha256(manifest)}

    def to_manifest(self) -> dict:
        manifest = asdict(self)
        manifest["config_schema_version"] = AGENT_CONFIG_SCHEMA_VERSION
        manifest["allowed_db_methods"] = list(self.allowed_db_methods)
        manifest["capabilities"] = self.capability_manifest()
        manifest["prompt"] = prompt_manifest(self.prompt_profile)
        manifest["query_plan"] = (
            protocol_manifest() if self.planner_mode == QUERY_PLAN_MODE else None
        )
        manifest["question_analysis"] = (
            question_analysis_manifest()
            if self.planner_mode == QUESTION_ANALYSIS_MODE else None
        )
        return manifest

    @property
    def sha256(self) -> str:
        return _manifest_sha256(self.to_manifest())


_PROFILES = {
    "legacy-e0": AgentConfig(
        profile="legacy-e0",
        experiment_variant="legacy",
        prompt_profile="legacy",
        use_db_hints=True,
        verified_final=False,
        capability_gate=False,
    ),
    "clean-e0": AgentConfig(
        profile="clean-e0",
        experiment_variant="e0",
        prompt_profile="basic",
        use_db_hints=False,
        verified_final=False,
        capability_gate=False,
    ),
    "clean-e1": AgentConfig(
        profile="clean-e1",
        experiment_variant="e1",
        prompt_profile="basic",
        use_db_hints=False,
        verified_final=True,
        capability_gate=False,
    ),
    "e4-r0": AgentConfig(
        profile="e4-r0",
        experiment_variant="e4-r0",
        prompt_profile="basic",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
    ),
    "e3-a": AgentConfig(
        profile="e3-a",
        experiment_variant="e3-a",
        prompt_profile="basic",
        use_db_hints=False,
        verified_final=False,
        capability_gate=False,
        query_pattern_mode="train-static-v1",
    ),
    "e3-rf": AgentConfig(
        profile="e3-rf",
        experiment_variant="e3-rf",
        prompt_profile="basic",
        use_db_hints=False,
        verified_final=False,
        capability_gate=False,
        few_shot_mode="none",
        query_pattern_mode="train-static-v1",
    ),
    "e3-c": AgentConfig(
        profile="e3-c",
        experiment_variant="e3-c",
        prompt_profile="basic",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
    ),
    "e3-f": AgentConfig(
        profile="e3-f",
        experiment_variant="e3-f",
        prompt_profile="basic",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        few_shot_mode="train-retrieval",
        query_pattern_mode="train-mined-v2",
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
    ),
    "e3-c-literal-check": AgentConfig(
        profile="e3-c-literal-check",
        experiment_variant="e3-c-literal-check",
        prompt_profile="basic",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        literal_verification_nudge=True,
    ),
    # E3-C + E3-A's train-only static patterns. The two were never combined:
    # E3-C deliberately switched patterns off to isolate the schema variable.
    # On the E0 stable-wrong set they recover largely disjoint questions
    # (6 and 10 respectively, overlapping on only 3), so the combination has
    # roughly +5 questions of complementary headroom.
    "e3-ac": AgentConfig(
        profile="e3-ac",
        experiment_variant="e3-ac",
        prompt_profile="basic",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        few_shot_mode="train-retrieval",
        query_pattern_mode="train-static-v1",
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
    ),
    # E3-C plus deterministic post-processing of the final SQL toward BIRD's
    # mined writing conventions. The conventions are also *stated* in E3-A's
    # static patterns, and e3-ac showed that stating them changes nothing
    # (24 vs 25 violations against e3-c); enforcing them here moves +5 questions.
    "e3-c-conv": AgentConfig(
        profile="e3-c-conv",
        experiment_variant="e3-c-conv",
        prompt_profile="basic",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION,
    ),
    # e3-c-conv plus the two legacy-prompt rules that survived a train audit.
    # Single variable against e3-c-conv: only the prompt profile differs, so the
    # deterministic post-processing stays identical on both sides.
    "e3-c-conv-rules": AgentConfig(
        profile="e3-c-conv-rules",
        experiment_variant="e3-c-conv-rules",
        prompt_profile="basic-conventions-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION,
    ),
    # Single variable against e3-c-conv-rules: the controller executes the exact
    # FINAL SQL itself and blocks on ERROR/EMPTY (ExecutionStatus, same criteria
    # AgentExecutionState.validate_final already used), telling the model to
    # redesign rather than resubmit on a timeout. Exists to test whether closing
    # the "the model never ran the query it actually submits" gap (see
    # docs/analysis/week_2026-08-18/sql_timeout_correction_2026-08-23.md) catches
    # inefficient SQL (correlated subquery instead of JOIN) before it reaches
    # scoring, without repeating E1's rejected mechanism (clean-e1,
    # e1_verified_summary.md): that one required the *model* to have pre-executed
    # the identical string and blocked on any revision, which fired on 90% of
    # questions for reasons unrelated to real problems. Here the controller does
    # the one execution itself at FINAL time -- no extra model turn on the
    # success path, and a block only fires on a genuine execution failure.
    "e3-c-conv-rules-final-gate": AgentConfig(
        profile="e3-c-conv-rules-final-gate",
        experiment_variant="e3-c-conv-rules-final-gate",
        prompt_profile="basic-conventions-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION,
        final_execution_gate=True,
    ),
    # Single variable against e3-c-conv-rules: the prompt says the tool calls are
    # really executed and their output comes back. Reading the captured reasoning for
    # all 496 dev questions, the model decides it cannot execute or cannot see results
    # in 113 of them (22.8%), and that group scores 57.5% against 70.0% for the rest;
    # 9 of the 21 failures that are the model's own fault carry the belief. Whether it
    # causes them is what this profile measures -- the correlation alone cannot say.
    "e3-c-conv-rules-toolconfirm": AgentConfig(
        profile="e3-c-conv-rules-toolconfirm",
        experiment_variant="e3-c-conv-rules-toolconfirm",
        prompt_profile="basic-conventions-toolconfirm-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION,
    ),
    # e3-c-conv-rules with the conventions restated as semantic criteria, and the
    # deterministic rewriting switched off: the model decides per question whether
    # a convention applies. The rewriter cannot -- it stripped DISTINCT from four
    # questions on the natural distribution that needed it, and its benefit ratio
    # fell from 8:1 on the adversarial subset to 7:4 outside it.
    "e3-c-semantic": AgentConfig(
        profile="e3-c-semantic",
        experiment_variant="e3-c-semantic",
        prompt_profile="basic-semantic-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
    ),
    # e3-c-conv-rules routed through the Responses API so each turn's reasoning is
    # recorded with the answer it produced. Diagnostic: the API path differs, so
    # its accuracy is not directly comparable until that is measured.
    "e3-c-rules-reasoning": AgentConfig(
        profile="e3-c-rules-reasoning",
        experiment_variant="e3-c-rules-reasoning",
        prompt_profile="basic-conventions-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION,
        reasoning_capture=REASONING_CAPTURE_MODE,
    ),
    # Treatment arm for the tool-confirmation experiment, paired with
    # e3-c-rules-reasoning as its control: same prompt difference as
    # e3-c-conv-rules-toolconfirm, but capturing reasoning at generation time.
    #
    # Capturing during the run rather than replaying afterwards is the whole point
    # here. A replay is not sampling-pinned, so it returns *a* reasoning chain for
    # the prompt, not the one behind the recorded answer -- on bird_93 the replay
    # queried the database while the original run never did, which is exactly the
    # behaviour this experiment is about. Both arms pay the Responses API path, so
    # they stay comparable to each other; neither is comparable to the Chat
    # Completions baselines.
    "e3-c-toolconfirm-reasoning": AgentConfig(
        profile="e3-c-toolconfirm-reasoning",
        experiment_variant="e3-c-toolconfirm-reasoning",
        prompt_profile="basic-conventions-toolconfirm-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION,
        reasoning_capture=REASONING_CAPTURE_MODE,
    ),
    # e3-c-conv-rules with the convention rewriting switched off, and nothing else
    # changed. It exists to split a confound in e3-c-recursive, which turned
    # recursion on and the rewriting off in the same profile: on the externally
    # corrected gold that profile gains +24 questions, the largest move measured,
    # and there is no way to tell from it whether recursion did that or whether
    # dropping the rewriting did.
    #
    # The suspicion is the latter. Scored against the corrected gold, the two rules
    # since disabled were worth -13 and -1 (see sql_postprocessing_rules_2026-08-16),
    # because they had been mined from gold that omits DISTINCT.
    #
    # This arm isolates that half cleanly. The other half does not isolate as
    # cleanly: e3-c-recursive also carries `basic-recursive-v1`, which has to name
    # the recursion tool for it to be reachable at all, so recursion-vs-not still
    # rides on a prompt difference.
    "e3-c-noconv": AgentConfig(
        profile="e3-c-noconv",
        experiment_variant="e3-c-noconv",
        prompt_profile="basic-conventions-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
    ),
    # Recursion v2: the leaf shares the parent's gated database handle. v1's
    # text-only leaf was handed the parent's ambiguity questions and, knowing
    # strictly less, moved accuracy 0.00pp on dev 500. Carries the convention
    # post-processing and audited rules so it builds on the current best.
    "e3-c-recursive-db": AgentConfig(
        profile="e3-c-recursive-db",
        experiment_variant="e3-c-recursive-db",
        prompt_profile="conventions-recursive-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION,
        recursion_mode="leaf-db-v1",
    ),
    # The recommended default for new runs: the highest-scoring chain arm
    # (e3-c-recursive-db, 88.10% mean on the corrected 498) plus the FINAL
    # execution gate, so a query that errors or times out inside the agent
    # loop comes back to the model with its actual error instead of reaching
    # scoring as a no_answer. A new profile rather than flipping the flag on
    # e3-c-recursive-db itself: agent_config_sha256 goes into every run
    # manifest, so mutating that profile would stop audit_run_configs.py from
    # recognising the existing eight-arm runs as the same configuration.
    #
    # Measured on 24 questions against e3-c-conv-rules (the same gate, one
    # layer down): 0.0pp accuracy, zero per-question flips, +10% tokens, and
    # the gate fired on 8.3% of questions -- see
    # docs/analysis/week_2026-08-18/timeout_agent_side_fix_2026-08-24.md.
    # It is here to keep no_answer from recurring, not as an accuracy
    # mechanism; the accuracy ceiling for an execution gate is ~1pp because
    # 60 of 61 remaining failures execute fine and are semantically wrong.
    "e3-c-recursive-db-final-gate": AgentConfig(
        profile="e3-c-recursive-db-final-gate",
        experiment_variant="e3-c-recursive-db-final-gate",
        prompt_profile="conventions-recursive-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION,
        recursion_mode="leaf-db-v1",
        final_execution_gate=True,
    ),
    # Single variable against e3-c-recursive-db: the convention artifact gains
    # keep_ties, which rewrites `ORDER BY x DESC LIMIT 1` into a form that keeps
    # every tied row. BIRD scores by set comparison, so the two forms agree
    # whenever the extremum is unique and diverge only on real ties -- where
    # LIMIT 1 keeps one arbitrary row and the rest of the answer is lost.
    #
    # Replaying the rewrite over three completed runs and rescoring measures
    # +5 / +5 / +4 questions (about +0.8 to +1.0pp), larger than layers 3 and 4
    # of the chain combined. Rejected three times before that on grounds that all
    # turned out to be wrong -- see docs/analysis/week_2026-08-18/
    # tie_rule_counterfactual_2026-08-25.md, which also records that this is
    # validated on dev only: there is no local train database, and reading train
    # gold *syntax* cannot settle a question about scored outcomes.
    "e3-c-recursive-db-keepties": AgentConfig(
        profile="e3-c-recursive-db-keepties",
        experiment_variant="e3-c-recursive-db-keepties",
        prompt_profile="conventions-recursive-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION_TIES,
        recursion_mode="leaf-db-v1",
    ),
    # Single variable against e3-c-recursive-db: RLM's context isolation is
    # dropped. Isolation exists so a sub-call runs in a small context and the
    # parent's does not overflow; measured utilisation on this task is ~4%
    # (analysisDetail/e5_a_context_store_smoke1.md), so the constraint it serves
    # does not exist here while both of its costs are measured -- the leaf cannot
    # notice a wrongly-framed sub-question (bird_173, bird_758), and its findings
    # reach the root only as prose, losing the rows it read (11 of 15 traced
    # failures had a leaf that was right; recursion_failure_traces_2026-08-24.md).
    #
    # Under leaf-open-v1 the leaf is shown the original question and returns its
    # raw observations alongside its answer. The prompt changes with it, so this
    # arm moves two things at once against e3-c-recursive-db -- deliberately: they
    # are the two halves of one design decision, and a prompt that still promises
    # isolation would misdescribe the tool. __post_init__ enforces the pairing.
    "e3-c-recursive-db-open": AgentConfig(
        profile="e3-c-recursive-db-open",
        experiment_variant="e3-c-recursive-db-open",
        prompt_profile="conventions-recursive-v2-open",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION,
        recursion_mode="leaf-open-v1",
    ),
    # printf('%.Nf', x) -> ROUND(x, N). A type fix, not a style one: printf
    # returns TEXT, ROUND returns REAL, and BIRD compares result tuples, so a
    # numerically perfect answer is scored wrong. Replayed over five completed
    # runs it fires 2-4 times and costs nothing at all -- 0 questions broken in
    # any run, which is rare here and follows from the rewrite changing only the
    # returned type, never the computation.
    "e3-c-recursive-db-types": AgentConfig(
        profile="e3-c-recursive-db-types",
        experiment_variant="e3-c-recursive-db-types",
        prompt_profile="conventions-recursive-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION_TYPES,
        recursion_mode="leaf-db-v1",
    ),
    # Both post-processing fixes together: the shipping candidate. Offline replay
    # over five runs gives +7 to +13 questions (+1.4 to +2.6pp) with the same two
    # costs every time (bird_633's all-NULL extremum, bird_82's WHERE differing
    # from gold's). Kept separate from the single-rule profiles so each rule's
    # contribution stays attributable.
    "e3-c-recursive-db-conv2": AgentConfig(
        profile="e3-c-recursive-db-conv2",
        experiment_variant="e3-c-recursive-db-conv2",
        prompt_profile="conventions-recursive-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION_BOTH,
        recursion_mode="leaf-db-v1",
    ),
    # Single variable against e3-c-recursive-db in behaviour, two in config
    # (planner_mode + the prompt that describes it, enforced as a pair below):
    # the model must read the question before writing any SQL.
    #
    # Targets the 18 of 46 root-caused failures that the question states and the
    # model did not act on -- entity-vs-row counting, filters named in the
    # question, percentage scaling, multi-part questions
    # (flatzero_23_root_causes_2026-08-25.md). Ceiling is 18-31 of 46, i.e.
    # +3.6 to +6.2pp, the largest target found so far; the realistic figure will
    # be well under that and stage one is there to find out.
    "e3-c-recursive-db-qa": AgentConfig(
        profile="e3-c-recursive-db-qa",
        experiment_variant="e3-c-recursive-db-qa",
        prompt_profile="conventions-qa-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION,
        recursion_mode="leaf-db-v1",
        planner_mode=QUESTION_ANALYSIS_MODE,
    ),
    # e3-c-recursive-db with reasoning_capture on, for causal tracing into *why*
    # depth-1 recursion doesn't move accuracy (five_layer_chain_results
    # 2026-08-19 §1: +0.3pp, inside noise, sign flips between repeats). Without
    # this the recursive-db trace shows that a leaf was called and what it
    # returned, but not what either side reasoned through to get there.
    # Single variable against e3-c-recursive-db: reasoning_capture on, nothing
    # else changes. Diagnostic caveat carries over from e3-c-rules-reasoning:
    # the Responses API path is not accuracy-comparable to Chat Completions.
    "e3-c-recursive-db-reasoning": AgentConfig(
        profile="e3-c-recursive-db-reasoning",
        experiment_variant="e3-c-recursive-db-reasoning",
        prompt_profile="conventions-recursive-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        sql_convention_mode=SQL_CONVENTION_VERSION,
        recursion_mode="leaf-db-v1",
        reasoning_capture=REASONING_CAPTURE_MODE,
    ),
    # First profile in the project that actually exposes RLM recursion. The
    # primitive has been in the REPL whenever capability_gate is off, but no
    # prompt profile ever named it — measured 0 invocations across 197 questions,
    # so every "recursion doesn't help" conclusion so far was about something else.
    # Single variable against e3-c: prompt names the tool, and the tool is present.
    "e3-c-recursive": AgentConfig(
        profile="e3-c-recursive",
        experiment_variant="e3-c-recursive",
        prompt_profile="basic-recursive-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        recursion_mode="leaf-v1",
    ),
    "e3-c-join-minimal": AgentConfig(
        profile="e3-c-join-minimal",
        experiment_variant="e3-c-join-minimal",
        prompt_profile="basic-join-minimal",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
    ),
    "e3-c-join-minimal-v2": AgentConfig(
        profile="e3-c-join-minimal-v2",
        experiment_variant="e3-c-join-minimal-v2",
        prompt_profile="basic-join-minimal-v2",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
    ),
    # E5-A: same information as e3-c, reachable through a read-only context
    # store instead of being concatenated into the prompt. Information-equivalence
    # smoke only — not an accuracy mechanism, and deliberately no search/slice/
    # compose (those are E5-B's variables).
    "e5-a": AgentConfig(
        profile="e5-a",
        experiment_variant="e5-a",
        prompt_profile="basic-context-store",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        context_mode="store-readonly",
    ),
    "e4-a": AgentConfig(
        profile="e4-a",
        experiment_variant="e4-a",
        prompt_profile="query-plan-v1",
        use_db_hints=False,
        verified_final=False,
        capability_gate=True,
        few_shot_mode="train-retrieval",
        query_pattern_mode="none",
        offline_metadata_mode="e3-f-schema-v4",
        schema_context_mode="offline-retrieval",
        reasoning_mode="query-plan",
        planner_mode=QUERY_PLAN_MODE,
    ),
}


def get_agent_config(profile: str) -> AgentConfig:
    try:
        return _PROFILES[profile]
    except KeyError as exc:
        choices = ", ".join(sorted(_PROFILES))
        raise ValueError(f"Unknown agent profile {profile!r}; choose one of: {choices}") from exc


def agent_profile_names() -> tuple[str, ...]:
    return tuple(sorted(_PROFILES))
