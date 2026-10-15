"""把校验通过的行分批写入 sync_records。每批单独一个事务。"""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.services.row_validator import ValidRow

# 规格要求每批 100–500 行。200 落在这个区间里。
RECORD_BATCH_SIZE = 200
# 对外只暴露这两类原因。数据库原文只进日志，不进 API。
BATCH_REASON_UNIQUE = "unique"
BATCH_REASON_WRITE = "write"

logger = logging.getLogger("syncflow.import")

_INSERT = text("""
    INSERT INTO sync_records (
        job_id, external_id, name, amount, record_date, created_at, updated_at
    ) VALUES (
        :job_id, :external_id, :name, :amount, :record_date, :created_at, :updated_at
    )
""")


@dataclass(frozen=True)
class BatchFailure:
    """一批写入失败。这一批已经回滚，其它批不受影响。"""

    batch_number: int
    row_count: int
    reason: str


@dataclass(frozen=True)
class BatchWriteResult:
    inserted_count: int
    failures: tuple[BatchFailure, ...]


class RecordRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def insert_in_batches(
        self,
        job_id: str,
        rows: Sequence[ValidRow],
        *,
        batch_size: int = RECORD_BATCH_SIZE,
        total_rows: int | None = None,
    ) -> BatchWriteResult:
        """按批提交。某一批冲突或写失败时只回滚该批，并留下批号和原因。"""
        if batch_size < 1:
            raise ValueError("batch_size 必须大于 0")

        total = total_rows if total_rows is not None else len(rows)
        inserted_count = 0
        processed = 0
        failures: list[BatchFailure] = []
        for batch_number, chunk in enumerate(_chunks(rows, batch_size), start=1):
            started = time.perf_counter()
            # csv_line 是文件行号（含表头）。data_rows 只计数据行，避免出现 row=3/2。
            csv_line = chunk[-1].row_number
            processed += len(chunk)
            try:
                with self.engine.begin() as conn:
                    _insert_batch(conn, job_id, chunk)
            except SQLAlchemyError as exc:
                # 原文含表名、索引名和键值，只写日志。调用方只看 reason。
                logger.error(
                    "job_id=%s batch=%s csv_line=%s data_rows=%s/%s result=failed elapsed_ms=%s db_error=%s",
                    job_id,
                    batch_number,
                    csv_line,
                    processed,
                    total,
                    _elapsed_ms(started),
                    _raw_db_error(exc),
                )
                failures.append(BatchFailure(
                    batch_number=batch_number,
                    row_count=len(chunk),
                    reason=_failure_reason(exc),
                ))
                continue
            inserted_count += len(chunk)
            logger.info(
                "job_id=%s batch=%s csv_line=%s data_rows=%s/%s result=ok elapsed_ms=%s",
                job_id,
                batch_number,
                csv_line,
                processed,
                total,
                _elapsed_ms(started),
            )
        return BatchWriteResult(inserted_count=inserted_count, failures=tuple(failures))


def _chunks(rows: Sequence[ValidRow], size: int):
    chunk: list[ValidRow] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _insert_batch(conn, job_id: str, rows: Sequence[ValidRow]) -> None:
    now = datetime.now(timezone.utc)
    conn.execute(_INSERT, [
        {
            "job_id": job_id,
            "external_id": row.external_id,
            "name": row.name,
            "amount": row.amount,
            "record_date": row.record_date,
            "created_at": now,
            "updated_at": now,
        }
        for row in rows
    ])


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _failure_reason(exc: SQLAlchemyError) -> str:
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ())
    # MySQL 1062 是重复键。其它写入失败不把驱动原文分类成具体约束。
    if args and args[0] == 1062:
        return BATCH_REASON_UNIQUE
    return BATCH_REASON_WRITE


def _raw_db_error(exc: SQLAlchemyError) -> str:
    orig = getattr(exc, "orig", None)
    text_value = str(orig or exc).strip()
    return text_value or exc.__class__.__name__
