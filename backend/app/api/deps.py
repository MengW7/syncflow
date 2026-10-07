from app.db.session import get_engine
from app.repositories.job_repo import JobRepository
from app.services.job_service import JobService


def get_job_service() -> JobService:
    return JobService(JobRepository(get_engine()))
