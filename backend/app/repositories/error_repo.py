"""把文件级和行级错误写入 sync_errors。"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

_INSERT = text("""
    INSERT INTO sync_errors (
        job_id, `row_number`, field_name, error_code, error_message, raw_row, created_at
    ) VALUES (
        :job_id, :row_number, :field_name, :error_code, :error_message,
        CAST(:raw_row AS JSON), :created_at
    )
""")

_MESSAGE_LIMIT = 512


@dataclass(frozen=True)
class ErrorToSave:
    """一行待写入的错误。文件级错误的 row_number 和 field_name 都是 None。"""

    row_number: int | None
    field_name: str | None
    error_code: str
    error_message: str
    raw_row: dict | None = None


class ErrorRepository:
    def insert_many(self, conn, job_id: str, errors: Sequence[ErrorToSave]) -> None:
        """在调用方的事务里写入。没有错误时什么都不做。"""
        if not errors:
            return
        now = datetime.now(timezone.utc)
        conn.execute(_INSERT, [
            {
                "job_id": job_id,
                "row_number": error.row_number,
                "field_name": error.field_name,
                "error_code": error.error_code,
                "error_message": error.error_message[:_MESSAGE_LIMIT],
                "raw_row": _json_or_none(error.raw_row),
                "created_at": now,
            }
            for error in errors
        ])

    def list_for_job(
        self,
        engine: Engine,
        job_id: str,
        *,
        page: int,
        page_size: int,
    ) -> list[dict]:
        """按行号、id 升序分页。空行号排在有行号的记录前面。"""
        offset = (page - 1) * page_size
        query = text("""
            SELECT job_id, `row_number`, field_name, error_code, error_message, raw_row, created_at
            FROM sync_errors
            WHERE job_id = :job_id
            ORDER BY `row_number` ASC, id ASC
            LIMIT :limit OFFSET :offset
        """)
        with engine.connect() as conn:
            rows = conn.execute(query, {
                "job_id": job_id,
                "limit": page_size,
                "offset": offset,
            }).mappings().all()
        return [dict(row) for row in rows]

    def count_for_job(self, engine: Engine, job_id: str) -> int:
        query = text("SELECT COUNT(*) FROM sync_errors WHERE job_id = :job_id")
        with engine.connect() as conn:
            return conn.execute(query, {"job_id": job_id}).scalar() or 0


def _json_or_none(raw_row: dict | None) -> str | None:
    if raw_row is None:
        return None
    return json.dumps(raw_row, ensure_ascii=False)
