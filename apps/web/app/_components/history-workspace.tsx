"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { apiRequest } from "@/lib/api";

type JobSummary = { id: string; title: string; source_type: "pasted_text"; created_at: string };
type VersionSummary = { id: string; job_description_id: string; job_title: string; accepted_suggestion_count: number; created_at: string };
type Notice = { tone: "error" | "info"; message: string } | null;

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Shanghai" }).format(new Date(value));
}

export function HistoryWorkspace() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<Notice>(null);

  const loadHistory = useCallback(async () => {
    try {
      const [jobsResponse, versionsResponse] = await Promise.all([
        apiRequest("/api/v1/jobs"),
        apiRequest("/api/v1/resume-versions")
      ]);
      setJobs((await jobsResponse.json()) as JobSummary[]);
      setVersions((await versionsResponse.json()) as VersionSummary[]);
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "无法读取历史记录。" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadHistory);
  }, [loadHistory]);

  return <main className="history-shell">
    <header className="intake-header"><Link className="wordmark intake-wordmark" href="/"><span className="wordmark-mark" aria-hidden="true">R</span><span>履历校准台</span></Link><div className="job-header-actions"><Link className="quiet-button state-link" href="/jobs">新建 JD 分析</Link><Link className="quiet-button state-link" href="/">返回工作台</Link></div></header>
    <section className="history-intro"><p className="eyebrow">历史记录</p><h1>回到任何一次认真做过的选择。</h1><p>JD、匹配证据和版本都只对你的登录会话可见。打开已分析的旧 JD 时，系统会展示当时绑定简历的匹配快照。</p></section>
    {notice ? <p className={`intake-notice intake-notice-${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>{notice.message}</p> : null}
    {loading ? <section className="intake-loading" aria-busy="true"><p className="eyebrow">正在读取</p><h2>正在恢复你的 JD 与版本记录…</h2></section> : <div className="history-grid">
      <section className="history-list"><div className="section-heading"><div><p className="eyebrow">保存的 JD</p><h2>岗位分析</h2></div><span className="count-label">{jobs.length} 条</span></div>{jobs.length === 0 ? <p className="list-empty">还没有保存的 JD。粘贴一份岗位描述后，它会出现在这里。</p> : jobs.map((job) => <Link className="history-row" href={`/jobs/${job.id}`} key={job.id}><strong>{job.title}</strong><span>用户粘贴 JD</span><small>{formatDate(job.created_at)}</small></Link>)}</section>
      <section className="history-list"><div className="section-heading"><div><p className="eyebrow">不可变快照</p><h2>岗位专属版本</h2></div><span className="count-label">{versions.length} 份</span></div>{versions.length === 0 ? <p className="list-empty">完成建议审核后生成的简历版本会出现在这里。</p> : versions.map((version) => <Link className="history-row" href={`/versions/${version.id}`} key={version.id}><strong>{version.job_title}</strong><span>已采纳 {version.accepted_suggestion_count} 项建议</span><small>{formatDate(version.created_at)}</small></Link>)}</section>
    </div>}
  </main>;
}
