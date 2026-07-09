import json

import pytest

from shared.experiment_tracking import (
    build_manifest,
    ensure_compatible_resume,
    manifest_path_for,
    write_manifest,
)


def test_manifest_rejects_incompatible_resume(tmp_path):
    dataset = tmp_path / "dataset.json"
    code = tmp_path / "code.py"
    result = tmp_path / "result.json"
    database_dir = tmp_path / "databases"
    database_dir.mkdir()
    dataset.write_text("[]", encoding="utf-8")
    code.write_text("VERSION = 1\n", encoding="utf-8")
    result.write_text("[]", encoding="utf-8")

    first = build_manifest(
        project_root=tmp_path,
        result_path=result,
        dataset_path=dataset,
        database_dir=database_dir,
        code_paths=[code],
        run_config={"model": "model-a"},
    )
    write_manifest(result, first)
    ensure_compatible_resume(result, first)

    second = build_manifest(
        project_root=tmp_path,
        result_path=result,
        dataset_path=dataset,
        database_dir=database_dir,
        code_paths=[code],
        run_config={"model": "model-b"},
    )
    with pytest.raises(RuntimeError, match="incompatible"):
        ensure_compatible_resume(result, second)

    saved = json.loads(manifest_path_for(result).read_text(encoding="utf-8"))
    assert saved["fingerprint"] == first["fingerprint"]
