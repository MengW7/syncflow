import hashlib
from pathlib import Path
from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import FileTooLarge, InvalidFileExtension


def save_upload_file(file: UploadFile, job_id: str) -> tuple[str, str, str]:
    """
    保存上传文件并校验安全规则。
    返回元组: (source_file_name, stored_file_path, file_sha256)
    """
    # 1. 扩展名判断与安全性校验（取客户端文件名）
    raw_filename = file.filename or ""
    parts = raw_filename.rsplit(".", 1)
    if len(parts) < 2 or parts[-1].lower() != "csv":
        raise InvalidFileExtension("仅支持上传 CSV 格式文件")

    # 2. 提取纯文件名 (去路径)，生成本地安全文件名
    source_file_name = Path(raw_filename).name
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target_path = upload_dir / f"{job_id}.csv"

    # 3. 边写盘边算 SHA-256，严格限制大小
    max_bytes = settings.max_upload_file_size_mb * 1024 * 1024
    total_bytes = 0
    hasher = hashlib.sha256()
    chunk_size = 64 * 1024  # 64KB 块读取

    try:
        with open(target_path, "wb") as buffer:
            while True:
                chunk = file.file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise FileTooLarge(f"文件大小超出限制 (最大 {settings.max_upload_file_size_mb} MB)")
                hasher.update(chunk)
                buffer.write(chunk)
    except FileTooLarge:
        # 超过限制，删除已写盘的残留文件
        if target_path.exists():
            target_path.unlink()
        raise
    except Exception:
        if target_path.exists():
            target_path.unlink()
        raise

    return source_file_name, str(target_path), hasher.hexdigest()