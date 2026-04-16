import re
from typing import Any, Literal, Dict
from decimal import Decimal
from datetime import datetime, date, time
from uuid import UUID
import psycopg
from django.conf import settings
from app.models import DBConnection


ALLOWED_KEYWORDS = {
    "select",
    "from",
    "where",
    "group",
    "by",
    "order",
    "limit",
    "as",
    "and",
    "or",
    "count",
    "sum",
    "avg",
    "min",
    "max",
}

FORBIDDEN_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "commit",
    "rollback",
    ";",
}

MAX_ROWS_PER_BATCH = 5000
QUERY_TIMEOUT_MS = 10000


def execute_sql_safely(
    sql: str,
    *,
    project_id: int,
    expected_result_type: Literal["scalar", "table"] = "scalar",
) -> Dict[str, Any]:
    """Execute sql safely"""

    _validate_sql(sql)
    try:
        db_connection = DBConnection.objects.get(
            project_id=project_id,
            is_active=True,
        )
        if db_connection.db_type != "postgres":
            raise ValueError("Only PostgreSQL databases are supported at this time")

    except DBConnection.DoesNotExist:
        raise ValueError("No active database connection found for this project")

    # Execute query and handle result types
    with psycopg.connect(
        dbname=db_connection.database_name,
        user=db_connection.username,
        password=db_connection.password,
        host=db_connection.host,
        port=db_connection.port,
        options=f"-c statement_timeout={QUERY_TIMEOUT_MS}",
    ) as conn:

        with conn.cursor() as cursor:
            cursor.execute(sql)

            if expected_result_type == "scalar":
                row = cursor.fetchone()
                value = row[0] if row else None
                return {
                    "status": "ok",
                    "result": json_safe(value),
                    "row_count": 1 if row else 0,
                }

            rows = []
            batch_size = MAX_ROWS_PER_BATCH

            # Fetch data in batches
            while True:
                batch = cursor.fetchmany(batch_size)

                if not batch:
                    break

                rows.extend(batch)

            columns = [desc[0] for desc in cursor.description]

            return {
                "status": "ok",
                "result": {
                    "columns": columns,
                    "rows": json_safe(rows),
                },
                "row_count": len(rows),
            }


def _validate_sql(sql: str) -> None:
    """Validate sql"""

    # Validate sql structure and safety rules
    if not sql or not isinstance(sql, str):
        raise ValueError("SQL must be a non-empty string")
    

     # Remove trailing semicolon safely
    sql = sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1]

    normalized = sql.lower().strip()

    # Single statement only
    if ";" in normalized:
        raise ValueError("Multiple SQL statements are not allowed")

    # Must start with SELECT
    if not (normalized.startswith("select") or normalized.startswith("with")):
        raise ValueError("Only SELECT queries are allowed")

    # Forbidden keywords
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", normalized):
            raise ValueError(f"Forbidden SQL keyword detected: {keyword}")

    # Token-level allowlist
    tokens = re.findall(r"[a-z_]+", normalized)
    for token in tokens:
        if token not in ALLOWED_KEYWORDS and not _is_identifier(token):
            raise ValueError(f"Unexpected SQL token: {token}")


def _is_identifier(token: str) -> bool:
    """Check identifier"""

    return bool(re.match(r"^[a-z_][a-z0-9_]*$", token))


def json_safe(value):
    """Convert value to json safe"""

    # Convert different data types to json serializable format

    # Primitives
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value

    # Numeric
    if isinstance(value, Decimal):
        return float(value)

    # Date and time
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    # UUID
    if isinstance(value, UUID):
        return str(value)

    # Binary
    if isinstance(value, (bytes, memoryview)):
        return value.hex()

    # Collections
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]

    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}

    # Fallback
    return str(value)
