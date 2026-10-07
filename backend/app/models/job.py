from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_serializer


# 任务状态枚举（仅包含本周要求的 4 种状态白名单）
class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# 基础模型：统一处理 datetime 序列化为 ISO 8601 UTC（带 Z 结尾）
class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer(
        "created_at",
        "started_at",
        "finished_at",
        check_fields=False,
    )
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# 列表查询参数校验
class JobListQuery(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    status: Optional[JobStatus] = None


# 对外 Schema：创建任务成功后的响应数据
class JobCreatedData(BaseSchema):
    id: str
    name: str
    status: JobStatus
    created_at: datetime


# 对外 Schema：列表单项（字段与详情一致，但排除冗余信息）
class JobListItem(BaseSchema):
    id: str
    name: str
    status: JobStatus
    source_file_name: str
    total_records: int
    success_records: int
    failed_records: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# 对外 Schema：分页元数据
class JobListMeta(BaseModel):
    page: int
    page_size: int
    total: int


# 对外 Schema：任务详情（严格要求文档的 13 个字段）
# 注意：不得包含 stored_file_path、file_sha256、idempotency_key
class JobDetail(BaseSchema):
    id: str
    name: str
    status: JobStatus
    source_file_name: str
    total_records: int
    success_records: int
    failed_records: int
    retry_count: int
    last_error_code: Optional[str] = None
    last_error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None