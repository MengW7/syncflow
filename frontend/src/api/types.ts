export type JobStatus = "PENDING" | "RUNNING" | "SUCCESS" | "FAILED";

export type JobListItem = {
  id: string;
  name: string;
  status: JobStatus;
  source_file_name: string;
  total_records: number;
  success_records: number;
  failed_records: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type JobDetail = JobListItem & {
  retry_count: number;
  last_error_code: string | null;
  last_error_message: string | null;
};

export type JobCreated = {
  id: string;
  name: string;
  status: JobStatus;
  created_at: string;
};

export type PageMeta = {
  page: number;
  page_size: number;
  total: number;
};

export type Envelope<T> = {
  data: T;
  meta: PageMeta | Record<string, never>;
};
