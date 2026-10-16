import { Link, useNavigate } from "react-router-dom";

import type { JobCreated } from "../api/types";
import { CreateJobForm } from "../components/CreateJobForm";

export function CreateJobPage() {
  const navigate = useNavigate();

  function handleCreated(job: JobCreated) {
    navigate(`/jobs/${job.id}`);
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h1>创建任务</h1>
      </div>
      <p>
        <Link to="/">返回列表</Link>
      </p>
      <CreateJobForm onCreated={handleCreated} />
    </section>
  );
}
