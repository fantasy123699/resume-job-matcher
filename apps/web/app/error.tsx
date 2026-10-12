"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="system-state">
      <span className="state-mark state-mark-error" aria-hidden="true" />
      <p className="eyebrow">加载遇到问题</p>
      <h1>页面暂时无法打开。</h1>
      <p>你的简历内容不会因这次加载失败而被修改。请重试，若问题持续出现，请返回稍后再试。</p>
      <button className="primary-button" type="button" onClick={() => reset()}>
        重新加载
      </button>
    </main>
  );
}
