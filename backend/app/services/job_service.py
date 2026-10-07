import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import UploadFile

from app.core.errors import (
    ErrorCode,
    InvalidFileExtension,
    InvalidRequest,
    JobNotFound,
)
from app.models.job import JobCreatedData, JobDetail, JobListItem, JobListMeta
from app.repositories.job_repo import JobRepository
from app.services.queue import queue_service
from app.services.storage import save_upload_file

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, repo: JobRepository):
        self.repo = repo

    def create_job(self, file: Optional[UploadFile], name: Optional[str] = None) -> JobCreatedData:
        """
        创建任务并触发副作用（严格按 Step 6 的 1~8 步执行）
        """
        # 1. 校验 file 存在，否则抛 INVALID_REQUEST
        if not file or not file.filename:
            raise InvalidRequest("必须上传文件")

        # 2. 校验扩展名 -> INVALID_FILE_EXTENSION (不分大小写)
        raw_filename = file.filename
        parts = raw_filename.rsplit(".", 1)
        if len(parts) < 2 or parts[-1].lower() != "csv":
            raise InvalidFileExtension("仅支持上传 CSV 格式文件")

        # 3. 生成 job_id（全局统一 UUID 36位）
        job_id = str(uuid.uuid4())

        # 4. 生成 / 截断 name (<=128; 空则例如 导入-{原始文件名去扩展}-{YYYY-MM-DD})
        base_name = Path(raw_filename).stem
        if not name or not name.strip():
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            job_name = f"导入-{base_name}-{today_str}"
        else:
            job_name = name.strip()
        job_name = job_name[:128]

        # 5. 流式保存文件 + 校验大小 + 算 sha256（超限会抛 FileTooLarge 并自动删残余文件）
        source_file_name, stored_file_path, file_sha256 = save_upload_file(file, job_id)

        # 6. repo.create(...)，初始 status=PENDING
        try:
            created_row = self.repo.create({
                "id": job_id,
                "name": job_name,
                "source_file_name": source_file_name,
                "stored_file_path": stored_file_path,
                "file_sha256": file_sha256,
            })
        except Exception:
            Path(stored_file_path).unlink(missing_ok=True)
            raise
        if created_row is None:
            Path(stored_file_path).unlink(missing_ok=True)
            raise RuntimeError("创建任务后未能读取记录")

        # 7. queue.enqueue(job_id)，失败则 repo.mark_failed(...)
        try:
            queue_service.enqueue_job(job_id)
        except Exception as exc:
            logger.exception("Redis 入队失败: job_id=%s, err=%s", job_id, exc)
            self.repo.mark_failed(
                job_id=job_id,
                code=ErrorCode.QUEUE_ENQUEUE_FAILED,
                message="任务已创建但加入队列失败",
            )
            # 重新获取更新后的记录以反映 FAILED 状态
            created_row = self.repo.get_by_id(job_id)

        # 8. 返回创建响应 DTO（严格只有 id/name/status/created_at）
        return JobCreatedData.model_validate(created_row)

    def get_job(self, job_id: str) -> JobDetail:
        """
        获取任务详情
        """
        job = self.repo.get_by_id(job_id)
        # 查不到 -> 抛出 JobNotFound
        if not job:
            raise JobNotFound(f"任务不存在: {job_id}")

        # 查到 -> 转成 JobDetail（自动根据白名单丢掉 stored_file_path 等内部字段）
        return JobDetail.model_validate(job)

    def list_jobs(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> Tuple[List[JobListItem], JobListMeta]:
        """
        分页查询任务列表
        """
        # query 已在外层通过 Pydantic schema 校验
        # 同时查 list + count
        rows = self.repo.list_jobs(status=status, page=page, page_size=page_size)
        total = self.repo.count_jobs(status=status)

        items = [JobListItem.model_validate(row) for row in rows]
        meta = JobListMeta(page=page, page_size=page_size, total=total)
        return items, meta