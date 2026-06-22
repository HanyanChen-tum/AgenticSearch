"""Local schema and document context for Spider2-Snow."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re

from spider2_snow_experiments import config
from spider2_snow_experiments.data import Spider2SnowExample


TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True)
class SchemaTable:
    database: str
    schema_name: str
    table_name: str
    description: str
    ddl: str

    @property
    def name_parts(self) -> tuple[str, ...]:
        return tuple(part.strip('"') for part in self.table_name.split(".") if part)

    @property
    def short_name(self) -> str:
        return self.name_parts[-1] if self.name_parts else self.table_name

    @property
    def schema_qualified_name(self) -> str:
        if len(self.name_parts) >= 2:
            return ".".join(self.name_parts[-2:])
        return f"{self.schema_name}.{self.short_name}"

    @property
    def full_name(self) -> str:
        if len(self.name_parts) >= 3:
            return ".".join(self.name_parts[-3:])
        return f"{self.database}.{self.schema_qualified_name}"

    @property
    def reference_names(self) -> set[str]:
        return {self.short_name, self.schema_qualified_name, self.full_name, self.table_name}

    @property
    def columns(self) -> tuple[str, ...]:
        start = self.ddl.find("(")
        end = self.ddl.rfind(")")
        if start < 0 or end <= start:
            return ()
        columns: list[str] = []
        for raw_line in self.ddl[start + 1 : end].splitlines():
            line = raw_line.strip().rstrip(",")
            if not line:
                continue
            upper_line = line.upper()
            if upper_line.startswith(("CONSTRAINT", "PRIMARY ", "FOREIGN ", "UNIQUE ", "KEY ")):
                continue
            quoted_match = re.match(r'"([^"]+)"\s+', line)
            if quoted_match:
                columns.append(quoted_match.group(1))
                continue
            plain_match = re.match(r"([A-Za-z_][\w$]*)\s+", line)
            if plain_match:
                columns.append(plain_match.group(1))
        return tuple(columns)

    @property
    def mixed_case_columns(self) -> set[str]:
        return {column for column in self.columns if column.upper() != column}

    @property
    def variant_columns(self) -> set[str]:
        start = self.ddl.find("(")
        end = self.ddl.rfind(")")
        if start < 0 or end <= start:
            return set()
        columns: set[str] = set()
        for raw_line in self.ddl[start + 1 : end].splitlines():
            line = raw_line.strip().rstrip(",")
            quoted_match = re.match(r'"([^"]+)"\s+VARIANT\b', line, re.IGNORECASE)
            if quoted_match:
                columns.add(quoted_match.group(1))
                continue
            plain_match = re.match(r"([A-Za-z_][\w$]*)\s+VARIANT\b", line, re.IGNORECASE)
            if plain_match:
                columns.add(plain_match.group(1))
        return columns


@dataclass(frozen=True)
class ExampleContext:
    schema_text: str
    document_text: str
    schema_tables: list[SchemaTable]


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[TRUNCATED]"


def load_schema_tables(
    db_id: str,
    databases_dir: str | Path = config.SPIDER2_SNOW_DATABASES,
) -> list[SchemaTable]:
    db_dir = Path(databases_dir) / db_id
    if not db_dir.exists():
        raise FileNotFoundError(f"Spider2-Snow database resource not found: {db_dir}")

    tables: list[SchemaTable] = []
    for ddl_path in sorted(db_dir.glob("*/DDL.csv")):
        schema_name = ddl_path.parent.name
        with ddl_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                table_name = (row.get("table_name") or "").strip()
                ddl = (row.get("DDL") or "").strip()
                if not table_name or not ddl:
                    continue
                tables.append(
                    SchemaTable(
                        database=db_id,
                        schema_name=schema_name,
                        table_name=table_name,
                        description=(row.get("description") or "").strip(),
                        ddl=ddl,
                    )
                )

    if not tables:
        raise FileNotFoundError(f"No DDL.csv tables found under: {db_dir}")
    return tables


def format_schema_tables(tables: list[SchemaTable]) -> str:
    blocks: list[str] = []
    for table in tables:
        header = (
            f"Database: {table.database}\n"
            f"Schema: {table.schema_name}\n"
            f"Table full name: {table.full_name}\n"
            f"Table schema-qualified name: {table.schema_qualified_name}\n"
            f"Table short name: {table.short_name}"
        )
        if table.description:
            header += f"\nDescription: {table.description}"
        blocks.append(f"{header}\nDDL:\n{table.ddl}")
    return "\n\n---\n\n".join(blocks)


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_RE.findall(text.replace("_", " "))
        if token.lower() not in STOPWORDS
    }


def _score_table(table: SchemaTable, question_tokens: set[str], question_lower: str) -> int:
    haystack = (
        f"{table.schema_name} {table.table_name} {table.full_name} "
        f"{table.short_name} {table.description} {table.ddl}"
    ).lower()
    table_tokens = _tokens(
        f"{table.schema_name} {table.table_name} {table.full_name} "
        f"{table.short_name} {table.description}"
    )
    score = 0
    for token in question_tokens:
        if token in table_tokens:
            score += 5
        if token in haystack:
            score += 1
    for name in (table.short_name, table.schema_qualified_name, table.full_name):
        name_text = name.lower().replace("_", " ")
        if name_text in question_lower:
            score += 8
    if table.short_name.lower() in question_lower:
        score += 8
    return score


def retrieve_schema_tables(
    question: str,
    tables: list[SchemaTable],
    *,
    top_k_tables: int,
) -> list[SchemaTable]:
    question_tokens = _tokens(question)
    question_lower = question.lower()
    ranked = sorted(
        tables,
        key=lambda table: (
            -_score_table(table, question_tokens, question_lower),
            table.schema_name,
            table.table_name,
        ),
    )
    return ranked[: max(1, top_k_tables)]


def read_external_document(
    external_knowledge: str | None,
    documents_dir: str | Path = config.SPIDER2_SNOW_DOCUMENTS,
    *,
    max_chars: int,
) -> str:
    if not external_knowledge:
        return ""
    path = Path(documents_dir) / external_knowledge
    if not path.exists():
        return f"[Missing external knowledge file: {external_knowledge}]"
    return _truncate(path.read_text(encoding="utf-8"), max_chars)


def build_example_context(
    example: Spider2SnowExample,
    *,
    databases_dir: str | Path = config.SPIDER2_SNOW_DATABASES,
    documents_dir: str | Path = config.SPIDER2_SNOW_DOCUMENTS,
    max_schema_chars: int = 60000,
    max_document_chars: int = 20000,
    top_k_tables: int | None = None,
) -> ExampleContext:
    all_tables = load_schema_tables(example.db_id, databases_dir)
    tables = (
        retrieve_schema_tables(example.question, all_tables, top_k_tables=top_k_tables)
        if top_k_tables is not None
        else all_tables
    )
    schema_text = _truncate(format_schema_tables(tables), max_schema_chars)
    document_text = read_external_document(
        example.external_knowledge,
        documents_dir,
        max_chars=max_document_chars,
    )
    return ExampleContext(
        schema_text=schema_text,
        document_text=document_text,
        schema_tables=tables,
    )
