import logging
import signal
import time

from app.db.session import engine
from app.repositories.job_repo import JobRepository
from app.services.queue import QueueService

logger = logging.getLogger("syncflow.worker")
_stop = False


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s service=worker %(message)s",
    )


def _request_stop(signum, _frame) -> None:
    global _stop
    _stop = True
    logger.info("worker stopping signal=%s", signum)


def process_job(repo: JobRepository, job_id: str) -> None:
    job_id = job_id.strip()
    if not job_id:
        logger.info("skip empty job id")
        return
    if not repo.mark_running(job_id):
        logger.info("job_id=%s skipped, status is not PENDING", job_id)
        return
    logger.info("job_id=%s status=RUNNING", job_id)
    try:
        updated = repo.mark_success(job_id)
    except Exception as exc:
        logger.error("job_id=%s mark SUCCESS failed error=%s", job_id, type(exc).__name__)
        repo.mark_failed(job_id, "INTERNAL_ERROR", "Worker 处理失败")
        return
    if not updated:
        logger.error("job_id=%s mark SUCCESS missed", job_id)
        repo.mark_failed(job_id, "INTERNAL_ERROR", "Worker 处理失败")
        return
    logger.info("job_id=%s status=SUCCESS", job_id)


def main() -> None:
    configure_logging()
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    logger.info("worker started")
    repo = JobRepository(engine)
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
                process_job(repo, job_id)
            except Exception as exc:
                logger.error("job_id=%s processing failed error=%s", job_id, type(exc).__name__)
    finally:
        queue.client.close()
        engine.dispose()
        logger.info("worker stopped")


if __name__ == "__main__":
    main()
