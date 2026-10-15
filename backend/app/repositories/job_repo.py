from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine


def _utcnow() -> datetime:
    """统一生成 UTC 时间"""
    return datetime.now(timezone.utc)


class JobRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        INSERT sync_jobs, status=PENDING, 计数 0
        """
        now = _utcnow()
        payload = {
            "id": job_data["id"],
            "name": job_data["name"],
            "status": "PENDING",
            "source_file_name": job_data["source_file_name"],
            "stored_file_path": job_data.get("stored_file_path", ""),
            "file_sha256": job_data.get("file_sha256", ""),
            "idempotency_key": job_data.get("idempotency_key"),
            "total_records": 0,
            "success_records": 0,
            "failed_records": 0,
            "retry_count": 0,
            "created_at": now,
            "updated_at": now,
        }

        query = text("""
            INSERT INTO sync_jobs (
                id, name, status, source_file_name, stored_file_path,
                file_sha256, idempotency_key, total_records, success_records,
                failed_records, retry_count, created_at, updated_at
            ) VALUES (
                :id, :name, :status, :source_file_name, :stored_file_path,
                :file_sha256, :idempotency_key, :total_records, :success_records,
                :failed_records, :retry_count, :created_at, :updated_at
            )
        """)

        with self.engine.begin() as conn:
            conn.execute(query, payload)

        return self.get_by_id(payload["id"])

    def get_by_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        SELECT 单行，没有则 None
        """
        query = text("SELECT * FROM sync_jobs WHERE id = :job_id LIMIT 1")
        with self.engine.connect() as conn:
            row = conn.execute(query, {"job_id": job_id}).mappings().first()
            return dict(row) if row else None

    def list_jobs(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        条件 + ORDER BY created_at DESC, id DESC + LIMIT/OFFSET
        """
        offset = (page - 1) * page_size
        where_clause = "WHERE status = :status" if status else ""

        sql = f"""
            SELECT * FROM sync_jobs
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
        """

        params = {"limit": page_size, "offset": offset}
        if status:
            params["status"] = status

        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
            return [dict(r) for r in rows]

    def count_jobs(self, status: Optional[str] = None) -> int:
        """
        给 meta.total 计算总记录数
        """
        where_clause = "WHERE status = :status" if status else ""
        sql = f"SELECT COUNT(*) FROM sync_jobs {where_clause}"

        params = {"status": status} if status else {}
        with self.engine.connect() as conn:
            return conn.execute(text(sql), params).scalar() or 0

    def mark_running(self, job_id: str, started_at: Optional[datetime] = None) -> bool:
        """
        PENDING -> RUNNING (Worker 用)
        """
        now = _utcnow()
        start_time = started_at or now

        query = text("""
            UPDATE sync_jobs
            SET status = 'RUNNING',
                started_at = :started_at,
                updated_at = :updated_at
            WHERE id = :job_id AND status = 'PENDING'
        """)

        with self.engine.begin() as conn:
            res = conn.execute(query, {
                "job_id": job_id,
                "started_at": start_time,
                "updated_at": now,
            })
            return res.rowcount > 0

    def mark_success(self, job_id: str, finished_at: Optional[datetime] = None) -> bool:
        """
        RUNNING -> SUCCESS (本周模拟)
        """
        now = _utcnow()
        finish_time = finished_at or now

        query = text("""
            UPDATE sync_jobs
            SET status = 'SUCCESS',
                finished_at = :finished_at,
                updated_at = :updated_at
            WHERE id = :job_id AND status = 'RUNNING'
        """)

        with self.engine.begin() as conn:
            res = conn.execute(query, {
                "job_id": job_id,
                "finished_at": finish_time,
                "updated_at": now,
            })
            return res.rowcount > 0

    def mark_failed(
        self,
        job_id: str,
        code: str,
        message: str,
        finished_at: Optional[datetime] = None,
    ) -> bool:
        """
        入队失败或 Worker 失败时更新错误信息。
        只改 PENDING / RUNNING，已终态的统计和说明保持原样。
        """
        now = _utcnow()
        finish_time = finished_at or now

        query = text("""
            UPDATE sync_jobs
            SET status = 'FAILED',
                last_error_code = :code,
                last_error_message = :message,
                finished_at = :finished_at,
                updated_at = :updated_at
            WHERE id = :job_id AND status IN ('PENDING', 'RUNNING')
        """)

        with self.engine.begin() as conn:
            res = conn.execute(query, {
                "job_id": job_id,
                "code": code,
                "message": message,
                "finished_at": finish_time,
                "updated_at": now,
            })
            return res.rowcount > 0

    def reclaim_stale_running(self, timeout_seconds: int) -> list[str]:
        """把超时仍停在 RUNNING 的任务标为 FAILED。返回被回收的任务 id。"""
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds 不能为负")
        now = _utcnow()
        deadline = now - timedelta(seconds=timeout_seconds)
        select_query = text("""
            SELECT id FROM sync_jobs
            WHERE status = 'RUNNING'
              AND (started_at IS NULL OR started_at < :deadline)
        """)
        update_query = text("""
            UPDATE sync_jobs
            SET status = 'FAILED',
                last_error_code = 'INTERNAL_ERROR',
                last_error_message = '任务处理超时',
                finished_at = :finished_at,
                updated_at = :updated_at
            WHERE id IN :ids AND status = 'RUNNING'
        """).bindparams(bindparam("ids", expanding=True))
        with self.engine.begin() as conn:
            ids = [row[0] for row in conn.execute(select_query, {"deadline": deadline})]
            if not ids:
                return []
            conn.execute(update_query, {
                "ids": ids,
                "finished_at": now,
                "updated_at": now,
            })
            return ids

    def finish_import(
        self,
        conn,
        job_id: str,
        *,
        status: str,
        total_records: int,
        success_records: int,
        failed_records: int,
        last_error_code: Optional[str] = None,
        last_error_message: Optional[str] = None,
        finished_at: Optional[datetime] = None,
    ) -> bool:
        """在调用方的事务里写入终态。计数、状态和 finished_at 同一次更新。"""
        now = _utcnow()
        finish_time = finished_at or now
        query = text("""
            UPDATE sync_jobs
            SET status = :status,
                total_records = :total_records,
                success_records = :success_records,
                failed_records = :failed_records,
                last_error_code = :last_error_code,
                last_error_message = :last_error_message,
                finished_at = :finished_at,
                updated_at = :updated_at
            WHERE id = :job_id AND status = 'RUNNING'
        """)
        res = conn.execute(query, {
            "job_id": job_id,
            "status": status,
            "total_records": total_records,
            "success_records": success_records,
            "failed_records": failed_records,
            "last_error_code": last_error_code,
            "last_error_message": last_error_message,
            "finished_at": finish_time,
            "updated_at": now,
        })
        return res.rowcount > 0