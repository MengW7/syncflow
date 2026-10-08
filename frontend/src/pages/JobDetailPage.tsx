import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, getJob } from "../api/client";
import type { JobDetail } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { formatLocalTime } from "../format";

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getJob(jobId)
      .then((result) => {
        if (!cancelled) {
          setJob(result.data);
        }
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setJob(null);
        setError(caught instanceof ApiError ? caught : new ApiError(0, "UNKNOWN", "加载任务失败"));
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, reloadKey]);

  if (loading) {
    return (
      <section className="panel">
        <p className="message">正在加载任务…</p>
      </section>
    );
  }

  if (error?.status === 404) {
    return (
      <section className="panel">
        <h1>任务不存在</h1>
        <p className="message">没有找到这个任务。</p>
        <Link to="/">返回列表</Link>
      </section>
    );
  }

  if (error || !job) {
    return (
      <section className="panel">
        <h1>无法加载任务</h1>
        <p className="message error" role="alert">
          {error?.message ?? "加载任务失败"}
        </p>
        <div className="actions">
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
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
    </section>
  );
}
