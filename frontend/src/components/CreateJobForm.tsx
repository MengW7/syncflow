import { useState } from "react";
import type { FormEvent } from "react";

import { ApiError, createJob } from "../api/client";
import type { JobCreated } from "../api/types";

export function CreateJobForm({ onCreated }: { onCreated: (job: JobCreated) => void }) {
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // React clears currentTarget when this handler returns, which happens at the first await.
    const form = event.currentTarget;
    if (!file) {
      setError("请选择 CSV 文件");
      return;
    }
    setPending(true);
    setError("");
    try {
      const result = await createJob(file, name);
      setName("");
      setFile(null);
      form.reset();
      onCreated(result.data);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "创建失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="create-form" onSubmit={handleSubmit}>
      <h2>创建任务</h2>
      <label>
        任务名称
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={128}
          placeholder="可不填，系统会自动生成"
        />
      </label>
      <label>
        CSV 文件
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </label>
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
