import type { JobStatus } from "../api/types";

import { JOB_STATUS_LABEL } from "./jobStatusLabel";

const KNOWN = new Set<string>(Object.keys(JOB_STATUS_LABEL));

export function StatusBadge({ status }: { status: string }) {
  const label = KNOWN.has(status) ? JOB_STATUS_LABEL[status as JobStatus] : status;
  const tone = KNOWN.has(status) ? status.toLowerCase() : "unknown";
  return <span className={`status status-${tone}`}>{label}</span>;
}
