import redis
from app.core.config import settings


class QueueService:
    def __init__(self, socket_timeout: float | None = 2):
        addr = settings.redis_addr.strip()
        host, sep, port_text = addr.rpartition(":")
        host = host if sep else addr
        port = int(port_text) if sep else 6379

        self.client = redis.Redis(
            host=host,
            port=port,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=socket_timeout,
        )

    def enqueue_job(self, job_id: str) -> None:
        """
        向 Redis 列表左侧推送 job_id (LPUSH)
        """
        self.client.lpush(settings.job_queue_key, str(job_id))

    def dequeue_job(self, timeout: int = 5) -> str | None:
        """从右侧阻塞取出任务 id。配合 LPUSH 时先入队的先被处理。"""
        item = self.client.brpop(settings.job_queue_key, timeout=timeout)
        if not item:
            return None
        _key, job_id = item
        return str(job_id) if job_id else None


queue_service = QueueService()