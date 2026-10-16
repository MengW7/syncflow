import type { JobStatus } from "../api/types";

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  PENDING: "等待中",
  RUNNING: "处理中",
  SUCCESS: "已完成",
  PARTIAL_SUCCESS: "部分成功",
  FAILED: "失败",
};
