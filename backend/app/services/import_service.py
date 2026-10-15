"""把一个已创建的任务导入 MySQL：解析、分批写入、错误记录、终态统计。

文件级失败不写 sync_records，计数保持 0，只记一条 row_number 为空的错误。
行级失败继续处理其它行。total = success + failed。
"""

import logging
from dataclasses import dataclass

from sqlalchemy.engine import Engine

from app.core.errors import ErrorCode, JobNotFound
from app.repositories.error_repo import ErrorRepository, ErrorToSave
from app.repositories.job_repo import JobRepository
from app.repositories.record_repo import (
    BATCH_REASON_UNIQUE,
    RECORD_BATCH_SIZE,
    BatchFailure,
    RecordRepository,
)
from app.services.row_validator import ParsedCsv, parse_csv

_MESSAGE_LIMIT = 512
logger = logging.getLogger("syncflow.import")


@dataclass(frozen=True)
class ImportResult:
    job_id: str
    status: str | None
    total_records: int
    success_records: int
    failed_records: int
    skipped: bool = False


class ImportService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.jobs = JobRepository(engine)
        self.records = RecordRepository(engine)
        self.errors = ErrorRepository()

    def import_job(self, job_id: str, *, batch_size: int = RECORD_BATCH_SIZE) -> ImportResult:
        """处理一个 PENDING 任务。不是 PENDING 时直接跳过，避免重复写入。"""
        job = self.jobs.get_by_id(job_id)
        if job is None:
            raise JobNotFound(f"任务不存在: {job_id}")
        if not self.jobs.mark_running(job_id):
            return ImportResult(
                job_id=job_id,
                status=job["status"],
                total_records=int(job["total_records"]),
                success_records=int(job["success_records"]),
                failed_records=int(job["failed_records"]),
                skipped=True,
            )

        parsed = parse_csv(job["stored_file_path"])
        if parsed.file_error is not None:
            logger.info("job_id=%s file_error=%s", job_id, parsed.file_error.code.value)
            return self._finish_file_error(job_id, parsed)

        invalid_rows = len({error.row_number for error in parsed.errors})
        total_rows = len(parsed.accepted) + invalid_rows
        logger.info(
            "job_id=%s rows=%s accepted=%s",
            job_id,
            total_rows,
            len(parsed.accepted),
        )
        written = self.records.insert_in_batches(
            job_id,
            parsed.accepted,
            batch_size=batch_size,
            total_rows=total_rows,
        )
        failed_in_batches = sum(failure.row_count for failure in written.failures)
        success = written.inserted_count
        failed = invalid_rows + failed_in_batches
        status = _terminal_status(success, failed)
        last_code, last_message = _batch_failure_summary(written.failures)
        self._finish(
            job_id,
            errors=_row_errors(parsed) + _batch_errors(written.failures),
            status=status,
            total_records=success + failed,
            success_records=success,
            failed_records=failed,
            last_error_code=last_code,
            last_error_message=last_message,
        )
        return ImportResult(
            job_id=job_id,
            status=status,
            total_records=success + failed,
            success_records=success,
            failed_records=failed,
        )

    def _finish_file_error(self, job_id: str, parsed: ParsedCsv) -> ImportResult:
        error = parsed.file_error
        assert error is not None
        self._finish(
            job_id,
            errors=[ErrorToSave(
                row_number=None,
                field_name=None,
                error_code=error.code.value,
                error_message=error.message,
            )],
            status="FAILED",
            total_records=0,
            success_records=0,
            failed_records=0,
            last_error_code=error.code.value,
            last_error_message=error.message,
        )
        return ImportResult(
            job_id=job_id,
            status="FAILED",
            total_records=0,
            success_records=0,
            failed_records=0,
        )

    def _finish(
        self,
        job_id: str,
        *,
        errors: list[ErrorToSave],
        status: str,
        total_records: int,
        success_records: int,
        failed_records: int,
        last_error_code: str | None,
        last_error_message: str | None,
    ) -> None:
        with self.engine.begin() as conn:
            self.errors.insert_many(conn, job_id, errors)
            updated = self.jobs.finish_import(
                conn,
                job_id,
                status=status,
                total_records=total_records,
                success_records=success_records,
                failed_records=failed_records,
                last_error_code=last_error_code,
                last_error_message=_clip(last_error_message),
            )
            if not updated:
                raise RuntimeError(f"任务不是 RUNNING，不能写入终态: {job_id}")


def _terminal_status(success: int, failed: int) -> str:
    if success > 0 and failed == 0:
        return "SUCCESS"
    if success > 0 and failed > 0:
        return "PARTIAL_SUCCESS"
    return "FAILED"


def _row_errors(parsed: ParsedCsv) -> list[ErrorToSave]:
    return [
        ErrorToSave(
            row_number=error.row_number,
            field_name=error.field_name,
            error_code=error.code.value,
            error_message=error.message,
            raw_row=error.raw_row,
        )
        for error in parsed.errors
    ]


def _batch_errors(failures: tuple[BatchFailure, ...]) -> list[ErrorToSave]:
    return [
        ErrorToSave(
            row_number=None,
            field_name=None,
            error_code=ErrorCode.INTERNAL_ERROR.value,
            error_message=_batch_message(failure),
            raw_row={"batch_number": failure.batch_number, "row_count": failure.row_count},
        )
        for failure in failures
    ]


def _batch_failure_summary(failures: tuple[BatchFailure, ...]) -> tuple[str | None, str | None]:
    if not failures:
        return None, None
    if len(failures) == 1:
        return ErrorCode.INTERNAL_ERROR.value, _batch_message(failures[0])
    return ErrorCode.INTERNAL_ERROR.value, _clip(_batch_summary(failures))


def _batch_message(failure: BatchFailure) -> str:
    if failure.reason == BATCH_REASON_UNIQUE:
        reason = "唯一约束冲突"
    else:
        reason = "写入失败"
    return f"第 {failure.batch_number} 批写入失败（{reason}）"


def _batch_summary(failures: tuple[BatchFailure, ...]) -> str:
    numbers = "、".join(str(failure.batch_number) for failure in failures)
    return f"第 {numbers} 批写入失败，共 {len(failures)} 批"


def _clip(message: str | None) -> str | None:
    if message is None or len(message) <= _MESSAGE_LIMIT:
        return message
    # 批号列表放不下时保留批数，避免截断后丢掉「共几批」。
    if message.startswith("第 ") and "共 " in message:
        count = message.rsplit("共 ", 1)[-1]
        return f"共 {count}"[:_MESSAGE_LIMIT]
    return message[:_MESSAGE_LIMIT]
