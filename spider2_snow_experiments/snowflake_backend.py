"""Snowflake execution helpers for Spider2-Snow."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from spider2_snow_experiments import config


PLACEHOLDER_VALUES = {"your_username", "your_password", ""}


def load_snowflake_credentials(path: str | Path) -> dict[str, Any]:
    credential_path = Path(path)
    credentials: dict[str, Any] = {}
    if credential_path.exists():
        with credential_path.open("r", encoding="utf-8") as file:
            credentials.update(json.load(file))

    env_map = {
        "user": "SNOWFLAKE_USER",
        "password": "SNOWFLAKE_PASSWORD",
        "account": "SNOWFLAKE_ACCOUNT",
        "authenticator": "SNOWFLAKE_AUTHENTICATOR",
        "warehouse": "SNOWFLAKE_WAREHOUSE",
        "role": "SNOWFLAKE_ROLE",
    }
    for key, env_name in env_map.items():
        value = os.getenv(env_name)
        if value:
            credentials[key] = value

    missing = [
        key
        for key in ("user", "password", "account")
        if credentials.get(key) in PLACEHOLDER_VALUES
    ]
    if missing:
        raise ValueError(
            "Snowflake credentials are not configured. Set "
            "SPIDER2_SNOW_CREDENTIAL_PATH or SNOWFLAKE_USER/SNOWFLAKE_PASSWORD/"
            f"SNOWFLAKE_ACCOUNT. Missing: {', '.join(missing)}"
        )
    return credentials


def execute_sql(
    db_id: str,
    sql: str,
    *,
    credential_path: str | Path = config.DEFAULT_CREDENTIAL_PATH,
    timeout: int = 60,
    max_rows: int | None = None,
) -> dict[str, Any]:
    try:
        import snowflake.connector
    except ImportError as exc:
        raise ImportError(
            "snowflake-connector-python is required for --execute."
        ) from exc

    credentials = load_snowflake_credentials(credential_path)
    connection_kwargs = {
        key: value
        for key, value in credentials.items()
        if key != "session_parameters"
    }
    session_parameters = credentials.get("session_parameters", {}).copy()
    session_parameters["STATEMENT_TIMEOUT_IN_SECONDS"] = timeout
    connection_kwargs["session_parameters"] = session_parameters

    conn = snowflake.connector.connect(database=db_id, **connection_kwargs)
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        rows = cursor.fetchmany(max_rows) if max_rows else cursor.fetchall()
        columns = [column[0] for column in cursor.description or []]
        return {
            "columns": columns,
            "answer": [list(row) for row in rows],
            "error": None,
        }
    except Exception as error:
        return {"columns": [], "answer": None, "error": str(error)}
    finally:
        cursor.close()
        conn.close()
