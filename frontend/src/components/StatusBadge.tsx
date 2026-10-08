import type { JobStatus } from "../api/types";

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  PENDING: "等待中",
  RUNNING: "处理中",
  SUCCESS: "已完成",
  FAILED: "失败",
};

const KNOWN = new Set<string>(Object.keys(JOB_STATUS_LABEL));

export function StatusBadge({ status }: { status: string }) {
  const label = KNOWN.has(status) ? JOB_STATUS_LABEL[status as JobStatus] : status;
  const tone = KNOWN.has(status) ? status.toLowerCase() : "unknown";
  return <span className={`status status-${tone}`}>{label}</span>;
}
