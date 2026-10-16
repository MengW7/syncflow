import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ApiError, getJobErrors } from "../api/client";
import type { JobError, PageMeta } from "../api/types";

const PAGE_SIZE = 20;

function readPage(value: string | null): number | null {
  if (!value) {
    return 1;
  }
  if (!/^[1-9]\d*$/.test(value)) {
    return null;
  }
  return Number(value);
}

function summarizeRawRow(raw: JobError["raw_row"]): string {
  if (!raw) {
    return "-";
  }
  const text = JSON.stringify(raw);
  if (text.length <= 120) {
    return text;
  }
  return `${text.slice(0, 117)}...`;
}

export function JobErrorsPage() {
  const { jobId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const page = readPage(params.get("page"));
  const pageError = page === null ? "页码不正确" : "";
  const [reloadKey, setReloadKey] = useState(0);
  const requestKey = `${jobId}:${page ?? "invalid"}:${reloadKey}`;
  const [snapshot, setSnapshot] = useState<{
    key: string;
    items: JobError[];
    meta: PageMeta | null;
    error: ApiError | null;
  }>({ key: "", items: [], meta: null, error: null });
  const loading = !pageError && snapshot.key !== requestKey;
  const items = loading ? [] : snapshot.items;
  const meta = loading ? null : snapshot.meta;
  const error = loading ? null : snapshot.error;

  useEffect(() => {
    if (pageError || page === null) {
      return;
    }

    const key = requestKey;
    let cancelled = false;
    getJobErrors(jobId, { page, pageSize: PAGE_SIZE })
      .then((result) => {
        if (cancelled) {
          return;
        }
        setSnapshot({ key, items: result.data, meta: result.meta, error: null });
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setSnapshot({
          key,
          items: [],
          meta: null,
          error: caught instanceof ApiError ? caught : new ApiError(0, "UNKNOWN", "加载错误明细失败"),
        });
      });

    return () => {
      cancelled = true;
    };
  }, [jobId, page, pageError, requestKey]);

  function updatePage(nextPage: number) {
    const query = new URLSearchParams(params);
    if (nextPage > 1) {
      query.set("page", String(nextPage));
    } else {
      query.delete("page");
    }
    setParams(query);
  }

  const total = meta?.total ?? 0;
  const currentPage = meta?.page ?? page ?? 1;
  const canPrev = currentPage > 1;
  const canNext = meta ? currentPage * PAGE_SIZE < total : false;

  return (
    <section className="panel">
      <div className="panel-head">
        <h1>错误明细</h1>
      </div>
      <p>
        <Link to={`/jobs/${jobId}`}>返回详情</Link>
      </p>

      {!pageError && loading ? <p className="message">正在加载错误明细…</p> : null}

      {pageError ? (
        <div className="message error" role="alert">
          <p>{pageError}</p>
          <button type="button" onClick={() => updatePage(1)}>
            回到第一页
          </button>
        </div>
      ) : null}

      {!pageError && !loading && error?.status === 404 ? (
        <div>
          <h2>任务不存在</h2>
          <p className="message">没有找到这个任务。</p>
          <Link to="/">返回列表</Link>
        </div>
      ) : null}

      {!pageError && !loading && error && error.status !== 404 ? (
        <div className="message error" role="alert">
          <p>{error.message}</p>
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
            重试
          </button>
        </div>
      ) : null}

      {!pageError && !loading && !error && total === 0 ? (
        <div className="empty">
          <p>没有错误记录。</p>
        </div>
      ) : null}

      {!pageError && !loading && !error && items.length > 0 ? (
        <div className="table-wrap">
          <table className="job-table">
            <thead>
              <tr>
                <th>行号</th>
                <th>字段</th>
                <th>错误码</th>
                <th>错误消息</th>
                <th>原始行</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={`${item.row_number ?? "file"}-${item.field_name ?? ""}-${item.error_code}-${index}`}>
                  <td data-label="行号">{item.row_number ?? "-"}</td>
                  <td data-label="字段">{item.field_name ?? "-"}</td>
                  <td data-label="错误码">{item.error_code}</td>
                  <td data-label="错误消息">{item.error_message}</td>
                  <td className="raw-summary" data-label="原始行">
                    {summarizeRawRow(item.raw_row)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {!pageError && !loading && !error && total > 0 && items.length === 0 ? (
        <p className="message">这一页没有错误记录。</p>
      ) : null}

      {!pageError && !loading && !error && total > 0 ? (
        <div className="pager">
          <button type="button" disabled={!canPrev} onClick={() => updatePage(currentPage - 1)}>
            上一页
          </button>
          <span>
            第 {currentPage} 页，共 {total} 条
          </span>
          <button type="button" disabled={!canNext} onClick={() => updatePage(currentPage + 1)}>
            下一页
          </button>
        </div>
      ) : null}
    </section>
  );
}
