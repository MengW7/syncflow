import redis
from app.core.config import settings


class QueueService:
    def __init__(self):
        addr = settings.redis_addr.strip()
        host, sep, port_text = addr.rpartition(":")
        host = host if sep else addr
        port = int(port_text) if sep else 6379

        self.client = redis.Redis(
            host=host,
            port=port,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    def enqueue_job(self, job_id: str) -> None:
        """
        向 Redis 列表左侧推送 job_id (LPUSH)
        """
        self.client.lpush(settings.job_queue_key, str(job_id))


queue_service = QueueService()