import Link from "next/link";

export default function NotFound() {
  return (
    <main className="system-state">
      <span className="state-mark" aria-hidden="true" />
      <p className="eyebrow">404</p>
      <h1>这个页面还没有被校准。</h1>
      <p>请检查地址，或返回工作台继续处理你的简历版本。</p>
      <Link className="primary-button state-link" href="/">
        返回工作台
      </Link>
    </main>
  );
}
