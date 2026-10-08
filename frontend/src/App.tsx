import { Link, Route, Routes } from "react-router-dom";

import { JobDetailPage } from "./pages/JobDetailPage";
import { JobListPage } from "./pages/JobListPage";
import { NotFoundPage } from "./pages/NotFoundPage";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link className="brand" to="/">
          SyncFlow
        </Link>
        <p>任务查询</p>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<JobListPage />} />
          <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
    </div>
  );
}
