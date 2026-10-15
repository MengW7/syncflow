import logging
import signal
import time

from app.core.config import settings
from app.db.session import engine
from app.services.import_service import ImportService
from app.services.queue import QueueService

logger = logging.getLogger("syncflow.worker")
_stop = False
_FAILED_MESSAGE = "Worker 处理失败"


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s service=worker %(message)s",
    )


def _request_stop(signum, _frame) -> None:
    global _stop
    _stop = True
    logger.info("worker stopping signal=%s", signum)


def reclaim_stale_jobs(importer: ImportService, timeout_seconds: int) -> list[str]:
    """启动时回收超时的 RUNNING。返回被标为 FAILED 的任务 id。"""
    job_ids = importer.jobs.reclaim_stale_running(timeout_seconds)
    for job_id in job_ids:
        logger.info("job_id=%s reclaimed stale RUNNING", job_id)
    return job_ids


def process_job(importer: ImportService, job_id: str) -> None:
    job_id = job_id.strip()
    if not job_id:
        logger.info("skip empty job id")
        return
    started = time.perf_counter()
    try:
        result = importer.import_job(job_id)
    except Exception as exc:
        # 堆栈只留在日志里。接口上的 last_error_message 用固定人话。
        logger.exception("job_id=%s import failed error=%s", job_id, type(exc).__name__)
        _mark_unexpected_failure(importer, job_id)
        return
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if result.skipped:
        logger.info(
            "job_id=%s skipped status=%s elapsed_ms=%s",
            job_id,
            result.status,
            elapsed_ms,
        )
        return
    logger.info(
        "job_id=%s status=%s total=%s success=%s failed=%s elapsed_ms=%s",
        job_id,
        result.status,
        result.total_records,
        result.success_records,
        result.failed_records,
        elapsed_ms,
    )


def _mark_unexpected_failure(importer: ImportService, job_id: str) -> None:
    try:
        importer.jobs.mark_failed(job_id, "INTERNAL_ERROR", _FAILED_MESSAGE)
    except Exception as exc:
        logger.error("job_id=%s mark FAILED failed error=%s", job_id, type(exc).__name__)


def main() -> None:
    configure_logging()
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    logger.info("worker started")
    importer = ImportService(engine)
    reclaim_stale_jobs(importer, settings.job_timeout_seconds)
    queue = QueueService(socket_timeout=None)
    try:
        while not _stop:
            try:
                job_id = queue.dequeue_job(timeout=5)
            except Exception as exc:
                logger.error("redis dequeue failed error=%s", type(exc).__name__)
                time.sleep(2)
                continue
            if not job_id or _stop:
                continue
            try:
                process_job(importer, job_id)
            except Exception as exc:
                logger.exception("job_id=%s processing failed error=%s", job_id, type(exc).__name__)
    finally:
        queue.client.close()
        engine.dispose()
        logger.info("worker stopped")


if __name__ == "__main__":
    main()
