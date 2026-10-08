import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError, listJobs } from "../api/client";
import type { JobCreated, JobListItem, PageMeta } from "../api/types";
import { CreateJobForm } from "../components/CreateJobForm";
import { JOB_STATUS_LABEL, StatusBadge } from "../components/StatusBadge";
import { formatLocalTime } from "../format";

const PAGE_SIZE = 20;
const STATUS_OPTIONS = ["", "PENDING", "RUNNING", "SUCCESS", "FAILED"] as const;

function readPage(value: string | null): number | null {
  if (!value) {
    return 1;
  }
  if (!/^[1-9]\d*$/.test(value)) {
    return null;
  }
  return Number(value);
}

export function JobListPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const page = readPage(params.get("page"));
  const statusKnown = status === "" || status in JOB_STATUS_LABEL;
  const [items, setItems] = useState<JobListItem[]>([]);
  const [meta, setMeta] = useState<PageMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<JobCreated | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (page === null || !statusKnown) {
      setLoading(false);
      setItems([]);
      setMeta(null);
      setError(page === null ? "页码不正确" : "不支持的任务状态");
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError("");
    listJobs({ page, pageSize: PAGE_SIZE, status: status || undefined })
      .then((result) => {
        if (cancelled) {
          return;
        }
        setItems(result.data);
        setMeta(result.meta);
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setItems([]);
        setMeta(null);
        setError(caught instanceof ApiError ? caught.message : "加载任务失败");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [page, status, statusKnown, reloadKey]);

  function updateQuery(next: { status?: string; page?: number }) {
    const query = new URLSearchParams(params);
    if (next.status !== undefined) {
      if (next.status) {
        query.set("status", next.status);
      } else {
        query.delete("status");
      }
    }
    if (next.page !== undefined) {
      if (next.page > 1) {
        query.set("page", String(next.page));
      } else {
        query.delete("page");
      }
    }
    setParams(query);
  }

  function handleCreated(job: JobCreated) {
    setCreated(job);
    setCreating(false);
    setReloadKey((value) => value + 1);
    updateQuery({ status: "", page: 1 });
  }

  const total = meta?.total ?? 0;
  const currentPage = meta?.page ?? page ?? 1;
  const canPrev = currentPage > 1;
  const canNext = meta ? currentPage * PAGE_SIZE < total : false;
  const showEmpty = !loading && !error && items.length === 0 && total === 0;

  return (
    <section className="panel">
      <div className="panel-head">
        <h1>任务列表</h1>
        <button type="button" className="primary" onClick={() => setCreating((open) => !open)}>
          {creating ? "收起" : "创建任务"}
        </button>
      </div>

      {creating ? <CreateJobForm onCreated={handleCreated} /> : null}
      {created ? (
        <p className="message">
          已创建任务「{created.name}」。
          <Link to={`/jobs/${created.id}`}>查看详情</Link>
        </p>
      ) : null}

      <label className="filter">
        状态
        <select
          value={statusKnown ? status : ""}
          onChange={(event) => updateQuery({ status: event.target.value, page: 1 })}
        >
          {STATUS_OPTIONS.map((value) => (
            <option key={value || "all"} value={value}>
              {value ? JOB_STATUS_LABEL[value] : "全部"}
            </option>
          ))}
        </select>
      </label>

      {loading ? <p className="message">正在加载任务…</p> : null}

      {!loading && error ? (
        <div className="message error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
            重试
          </button>
          {!statusKnown || page === null ? (
            <button type="button" onClick={() => updateQuery({ status: "", page: 1 })}>
              回到第一页
            </button>
          ) : null}
        </div>
      ) : null}

      {showEmpty ? (
        <div className="empty">
          <p>还没有任务。</p>
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            创建任务
          </button>
        </div>
      ) : null}

      {!loading && !error && items.length > 0 ? (
        <div className="table-wrap">
          <table className="job-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>状态</th>
                <th>文件名</th>
                <th>总数</th>
                <th>成功</th>
                <th>失败</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((job) => (
                <tr key={job.id}>
                  <td data-label="名称">{job.name}</td>
                  <td data-label="状态">
                    <StatusBadge status={job.status} />
                  </td>
                  <td data-label="文件名">{job.source_file_name}</td>
                  <td data-label="总数">{job.total_records}</td>
                  <td data-label="成功">{job.success_records}</td>
                  <td data-label="失败">{job.failed_records}</td>
                  <td data-label="创建时间">{formatLocalTime(job.created_at)}</td>
                  <td data-label="操作">
                    <Link to={`/jobs/${job.id}`}>详情</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {!loading && !error && total > 0 && items.length === 0 ? (
        <p className="message">这一页没有任务。</p>
      ) : null}

      {!loading && !error && total > 0 ? (
        <div className="pager">
          <button type="button" disabled={!canPrev} onClick={() => updateQuery({ page: currentPage - 1 })}>
            上一页
          </button>
          <span>
            第 {currentPage} 页，共 {total} 条
          </span>
          <button type="button" disabled={!canNext} onClick={() => updateQuery({ page: currentPage + 1 })}>
            下一页
          </button>
        </div>
      ) : null}
    </section>
  );
}
