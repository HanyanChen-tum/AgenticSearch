"""Reproducibility metadata and compatibility checks for experiment runs."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MANIFEST_VERSION = 1


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_files(paths: Iterable[str | Path], *, root: str | Path) -> str:
    root_path = Path(root).resolve()
    digest = hashlib.sha256()
    for raw_path in sorted((Path(path).resolve() for path in paths), key=str):
        digest.update(str(raw_path.relative_to(root_path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def database_fingerprint(
    database_dir: str | Path,
    dataset_path: str | Path,
) -> dict[str, Any]:
    """Hash database files referenced by the dataset, not unrelated databases."""
    database_dir = Path(database_dir).resolve()
    rows = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    db_ids = sorted({str(row["db_id"]) for row in rows})
    paths: list[Path] = []
    for db_id in db_ids:
        base = database_dir / db_id / db_id
        path = next(
            (base.with_suffix(ext) for ext in (".sqlite", ".db") if base.with_suffix(ext).exists()),
            None,
        )
        if path is None:
            raise FileNotFoundError(f"Database referenced by dataset not found: {base}")
        paths.append(path)
    return {
        "path": str(database_dir),
        "database_count": len(paths),
        "sha256": sha256_files(paths, root=database_dir),
    }


def git_revision(project_root: str | Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def manifest_path_for(result_path: str | Path) -> Path:
    path = Path(result_path)
    return path.with_name(f"{path.stem}.manifest.json")


def build_manifest(
    *,
    project_root: str | Path,
    result_path: str | Path,
    dataset_path: str | Path,
    database_dir: str | Path,
    code_paths: Iterable[str | Path],
    run_config: dict[str, Any],
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    dataset_path = Path(dataset_path).resolve()
    database_dir = Path(database_dir).resolve()
    stable = {
        "manifest_version": MANIFEST_VERSION,
        "dataset": {
            "path": str(dataset_path),
            "sha256": sha256_file(dataset_path),
        },
        "databases": database_fingerprint(database_dir, dataset_path),
        "code_sha256": sha256_files(code_paths, root=project_root),
        "run_config": run_config,
    }
    fingerprint = hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        **stable,
        "result_path": str(Path(result_path).resolve()),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision(project_root),
        "fingerprint": fingerprint,
    }


def ensure_compatible_resume(
    result_path: str | Path,
    expected_manifest: dict[str, Any],
) -> None:
    result_path = Path(result_path)
    manifest_path = manifest_path_for(result_path)
    if not result_path.exists():
        return
    if not manifest_path.exists():
        raise RuntimeError(
            f"Refusing to resume legacy result file without manifest: {result_path}. "
            "Use a new output path or remove the old result explicitly."
        )
    existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    if existing.get("fingerprint") != expected_manifest.get("fingerprint"):
        raise RuntimeError(
            "Refusing to mix incompatible experiment runs in one result file. "
            f"Existing fingerprint={existing.get('fingerprint')}, "
            f"current fingerprint={expected_manifest.get('fingerprint')}."
        )


def write_manifest(result_path: str | Path, manifest: dict[str, Any]) -> Path:
    path = manifest_path_for(result_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
