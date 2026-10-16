import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { ApiError, createJob } from "../api/client";
import type { JobCreated } from "../api/types";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const MAX_NAME_LENGTH = 128;

function isCsvFile(file: File): boolean {
  return file.name.toLowerCase().endsWith(".csv");
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    const value = bytes / 1024;
    return `${value.toFixed(value >= 10 ? 0 : 1)} KB`;
  }
  const value = bytes / (1024 * 1024);
  return `${value.toFixed(value >= 10 ? 0 : 1)} MB`;
}

function clientFileError(file: File): string {
  if (!isCsvFile(file)) {
    return "只支持 .csv 文件";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return "文件不能超过 10MB";
  }
  return "";
}

export function CreateJobForm({ onCreated }: { onCreated: (job: JobCreated) => void }) {
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] ?? null;
    setFile(next);
    setError(next ? clientFileError(next) : "");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("请选择 CSV 文件");
      return;
    }
    const fileError = clientFileError(file);
    if (fileError) {
      setError(fileError);
      return;
    }
    if (name.trim().length > MAX_NAME_LENGTH) {
      setError("任务名称最长 128 个字符");
      return;
    }
    setPending(true);
    setError("");
    try {
      const result = await createJob(file, name);
      onCreated(result.data);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "创建失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="create-form" onSubmit={handleSubmit}>
      <label>
        任务名称
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={MAX_NAME_LENGTH}
          placeholder="可不填，系统会自动生成"
          disabled={pending}
        />
      </label>
      <label>
        CSV 文件
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={handleFile}
          disabled={pending}
        />
      </label>
      {file ? (
        <p className="file-meta">
          已选择 {file.name}（{formatFileSize(file.size)}）
        </p>
      ) : null}
      {error ? (
        <p className="message error" role="alert">
          {error}
        </p>
      ) : null}
      <button className="primary" type="submit" disabled={pending}>
        {pending ? "正在创建…" : "提交"}
      </button>
    </form>
  );
}
