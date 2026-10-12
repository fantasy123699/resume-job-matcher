"use client";

export default function GlobalError({
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <main>
          <h1>应用暂时不可用</h1>
          <button type="button" onClick={() => reset()}>
            重试
          </button>
        </main>
      </body>
    </html>
  );
}
