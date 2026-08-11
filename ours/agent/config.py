"""Immutable configuration for DB-agent ablations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

from .prompts import prompt_manifest
from .query_plan import QUERY_PLAN_MODE, protocol_manifest
from .reasoning_capture import CAPTURE_MODE as REASONING_CAPTURE_MODE
from .sql_conventions import VERSION as SQL_CONVENTION_VERSION


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
        if self.sql_convention_mode not in {"none", SQL_CONVENTION_VERSION}:
            raise ValueError(f"Unknown SQL convention mode: {self.sql_convention_mode!r}")
        if self.reasoning_capture not in {"none", REASONING_CAPTURE_MODE}:
            raise ValueError(f"Unknown reasoning capture mode: {self.reasoning_capture!r}")
        if self.recursion_mode not in {"none", "leaf-v1", "leaf-db-v1"}:
            raise ValueError(f"Unknown recursion mode: {self.recursion_mode!r}")
        # The primitive was present in three earlier profiles but no prompt named
        # it, so it was never invoked. Requiring the prompt that documents it
        # prevents that silent no-op from recurring.
        if self.recursion_mode != "none" and self.prompt_profile not in {
            "basic-recursive-v1", "conventions-recursive-v1"
        }:
            raise ValueError(
                f"recursion_mode={self.recursion_mode!r} requires a prompt profile "
                "that documents recursive_llm"
            )
        if self.schema_context_mode == "offline-retrieval" and self.offline_metadata_mode == "none":
            raise ValueError("offline-retrieval requires an offline metadata artifact")
        if self.planner_mode not in {"none", QUERY_PLAN_MODE}:
            raise ValueError(f"Unknown planner mode: {self.planner_mode!r}")
        if self.planner_mode == QUERY_PLAN_MODE and self.prompt_profile != "query-plan-v1":
            raise ValueError("root-query-plan-v1 requires prompt_profile='query-plan-v1'")

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
