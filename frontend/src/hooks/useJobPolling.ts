import { useEffect, useState } from "react";

import { ApiError, getJob } from "../api/client";
import type { JobDetail, JobStatus } from "../api/types";

const POLL_INTERVAL_MS = 3000;

const TERMINAL: ReadonlySet<JobStatus> = new Set(["SUCCESS", "PARTIAL_SUCCESS", "FAILED"]);

export function useJobPolling(jobId: string) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;

    async function load(first: boolean) {
      try {
        const result = await getJob(jobId);
        if (cancelled) {
          return;
        }
        setJob(result.data);
        setError(null);
        if (!TERMINAL.has(result.data.status)) {
          timer = window.setTimeout(() => {
            void load(false);
          }, POLL_INTERVAL_MS);
        }
      } catch (caught: unknown) {
        if (cancelled) {
          return;
        }
        const next = caught instanceof ApiError ? caught : new ApiError(0, "UNKNOWN", "加载任务失败");
        // 已经显示过详情时保留数据，下一轮成功再清掉提示。没有数据或任务消失才整页报错。
        if (!first && next.status !== 404) {
          setError(next);
          timer = window.setTimeout(() => {
            void load(false);
          }, POLL_INTERVAL_MS);
          return;
        }
        setJob(null);
        setError(next);
      } finally {
        if (!cancelled && first) {
          setLoading(false);
        }
      }
    }

    void load(true);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [jobId]);

  return { job, loading, error };
}
