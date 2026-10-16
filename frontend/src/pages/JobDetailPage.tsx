import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { StatusBadge } from "../components/StatusBadge";
import { formatLocalTime } from "../format";
import { useJobPolling } from "../hooks/useJobPolling";

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const [attempt, setAttempt] = useState(0);
  return (
    <JobDetailBody
      key={`${jobId}:${attempt}`}
      jobId={jobId}
      onRetry={() => setAttempt((value) => value + 1)}
    />
  );
}

function JobDetailBody({ jobId, onRetry }: { jobId: string; onRetry: () => void }) {
  const { job, loading, error } = useJobPolling(jobId);
  const showErrors = job !== null && (job.failed_records > 0 || job.status === "FAILED");

  if (loading) {
    return (
      <section className="panel">
        <p className="message">正在加载任务…</p>
      </section>
    );
  }

  if (!job && error?.status === 404) {
    return (
      <section className="panel">
        <h1>任务不存在</h1>
        <p className="message">没有找到这个任务。</p>
        <Link to="/">返回列表</Link>
      </section>
    );
  }

  if (!job) {
    return (
      <section className="panel">
        <h1>无法加载任务</h1>
        <p className="message error" role="alert">
          {error?.message ?? "加载任务失败"}
        </p>
        <div className="actions">
          <button type="button" onClick={onRetry}>
            重试
          </button>
          <Link to="/">返回列表</Link>
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h1>{job.name}</h1>
        <StatusBadge status={job.status} />
      </div>
      <p>
        <Link to="/">返回列表</Link>
      </p>
      {error ? (
        <p className="message error" role="alert">
          刷新失败：{error.message}
        </p>
      ) : null}
      {job.status === "PENDING" || job.status === "RUNNING" ? (
        <p className="message">正在处理，每 3 秒自动刷新。</p>
      ) : null}
      <dl className="detail">
        <div>
          <dt>源文件名</dt>
          <dd>{job.source_file_name}</dd>
        </div>
        <div>
          <dt>总记录数</dt>
          <dd>{job.total_records}</dd>
        </div>
        <div>
          <dt>成功数</dt>
          <dd>{job.success_records}</dd>
        </div>
        <div>
          <dt>失败数</dt>
          <dd>{job.failed_records}</dd>
        </div>
        <div>
          <dt>创建时间</dt>
          <dd>{formatLocalTime(job.created_at)}</dd>
        </div>
        <div>
          <dt>开始时间</dt>
          <dd>{formatLocalTime(job.started_at)}</dd>
        </div>
        <div>
          <dt>结束时间</dt>
          <dd>{formatLocalTime(job.finished_at)}</dd>
        </div>
        <div>
          <dt>最近错误</dt>
          <dd>
            {job.last_error_code || job.last_error_message
              ? `${job.last_error_code ?? ""} ${job.last_error_message ?? ""}`.trim()
              : "无"}
          </dd>
        </div>
      </dl>
      {showErrors ? (
        <p className="actions">
          <Link to={`/jobs/${job.id}/errors`}>查看错误明细</Link>
        </p>
      ) : null}
    </section>
  );
}
