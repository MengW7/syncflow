import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="panel">
      <h1>页面不存在</h1>
      <p className="message">没有找到这个地址。</p>
      <Link to="/">返回任务列表</Link>
    </section>
  );
}
