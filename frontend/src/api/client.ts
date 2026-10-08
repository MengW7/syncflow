import type { Envelope, JobCreated, JobDetail, JobListItem, PageMeta } from "./types";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, "NETWORK", "网络请求失败，请检查连接后重试");
  }

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error =
      body !== null && typeof body === "object" && "error" in body
        ? (body as { error?: { code?: string; message?: string } }).error
        : undefined;
    throw new ApiError(
      response.status,
      error?.code ?? "UNKNOWN",
      error?.message ?? "请求失败",
    );
  }

  return body as T;
}

export function listJobs(query: {
  page: number;
  pageSize: number;
  status?: string;
}): Promise<Envelope<JobListItem[]> & { meta: PageMeta }> {
  const params = new URLSearchParams({
    page: String(query.page),
    page_size: String(query.pageSize),
  });
  if (query.status) {
    params.set("status", query.status);
  }
  return request(`/api/v1/jobs?${params.toString()}`);
}

export function getJob(jobId: string): Promise<Envelope<JobDetail>> {
  return request(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
}

export function createJob(file: File, name: string): Promise<Envelope<JobCreated>> {
  const form = new FormData();
  form.append("file", file);
  if (name.trim()) {
    form.append("name", name.trim());
  }
  return request("/api/v1/jobs", { method: "POST", body: form });
}
