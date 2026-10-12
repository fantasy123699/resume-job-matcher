"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiRequest } from "@/lib/api";

type ResumeSummary = {
  id: string;
  status: "pending_confirmation" | "confirmed";
  source_format: "text" | "docx" | "pdf";
  created_at: string;
};
type JobSummary = { id: string; title: string; source_type: "pasted_text"; created_at: string };
type VersionSummary = { id: string; job_description_id: string; job_title: string; accepted_suggestion_count: number; created_at: string };
type Notice = { tone: "error" | "info"; message: string } | null;

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeZone: "Asia/Shanghai" }).format(new Date(value));
}

export function DashboardWorkspace() {
  const [resumes, setResumes] = useState<ResumeSummary[]>([]);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<Notice>(null);

  const loadDashboard = useCallback(async () => {
    try {
      const [resumesResponse, jobsResponse, versionsResponse] = await Promise.all([
        apiRequest("/api/v1/resumes"),
        apiRequest("/api/v1/jobs"),
        apiRequest("/api/v1/resume-versions")
      ]);
      setResumes((await resumesResponse.json()) as ResumeSummary[]);
      setJobs((await jobsResponse.json()) as JobSummary[]);
      setVersions((await versionsResponse.json()) as VersionSummary[]);
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "无法读取工作台数据。" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadDashboard);
  }, [loadDashboard]);

  const confirmedResume = useMemo(
    () => resumes.find((resume) => resume.status === "confirmed") ?? null,
    [resumes]
  );
  const pendingResume = resumes.find((resume) => resume.status === "pending_confirmation") ?? null;
  const nextAction = confirmedResume === null
    ? { href: "/resumes", label: pendingResume === null ? "导入简历" : "确认简历事实", description: pendingResume === null ? "先导入一份简历，系统只保存你允许使用的原文。" : "仍有待确认的简历事实，确认后才能开始岗位匹配。" }
    : jobs.length === 0
      ? { href: "/jobs", label: "粘贴目标 JD", description: "简历已确认，下一步是粘贴一份有权使用的岗位描述。" }
      : versions.length === 0
        ? { href: `/jobs/${jobs[0].id}`, label: "继续审核建议", description: "打开最近的岗位分析，逐项决定是否采纳呈现顺序调整。" }
        : { href: `/versions/${versions[0].id}`, label: "查看最新版本", description: "你的岗位专属简历已生成，可随时查看与导出。" };

  return (
    <main className="workspace-shell">
      <aside className="workspace-sidebar" aria-label="主导航">
        <Link className="wordmark" href="/" aria-label="履历校准台首页"><span className="wordmark-mark" aria-hidden="true">R</span><span>履历校准台</span></Link>
        <div className="workspace-switcher"><span className="eyebrow">当前工作区</span><strong>我的求职准备</strong><span className="workspace-date">数据仅限当前登录账户</span></div>
        <nav className="main-navigation">
          <Link className="nav-item nav-item-active" href="/" aria-current="page"><span>工作台</span></Link>
          <Link className="nav-item" href="/resumes"><span>简历事实</span></Link>
          <Link className="nav-item" href="/jobs"><span>目标 JD</span></Link>
          <Link className="nav-item" href="/history"><span>历史记录</span></Link>
        </nav>
        <div className="sidebar-footnote"><span className="privacy-pulse" aria-hidden="true" /><p>只有已确认事实才会用于匹配、建议与导出。</p></div>
      </aside>

      <section className="workspace-main" aria-busy={loading}>
        <header className="workspace-header">
          <div><p className="eyebrow">工作台 / 真实数据</p><h1>从真实事实开始，继续下一步。</h1></div>
          <div className="header-actions"><Link className="quiet-button state-link" href="/history">查看历史</Link><Link className="primary-button state-link" href={nextAction.href}>{nextAction.label}</Link></div>
        </header>

        {notice ? <p className={`intake-notice intake-notice-${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>{notice.message}</p> : null}

        {loading ? <section className="intake-loading"><p className="eyebrow">正在读取</p><h2>正在整理你的简历、JD 与版本记录…</h2></section> : <>
          <section className="journey" aria-label="简历优化流程">
            <Step index={1} label="导入简历" state={resumes.length > 0 ? "done" : "active"} />
            <Step index={2} label="确认事实" state={confirmedResume ? "done" : resumes.length > 0 ? "active" : "next"} />
            <Step index={3} label="解析 JD" state={jobs.length > 0 ? "done" : confirmedResume ? "active" : "next"} />
            <Step index={4} label="审核修改" state={versions.length > 0 ? "done" : jobs.length > 0 ? "active" : "next"} />
            <Step index={5} label="导出版本" state={versions.length > 0 ? "active" : "next"} />
          </section>

          <section className="focus-band" aria-labelledby="next-action-heading">
            <div><p className="eyebrow">建议的下一步</p><h2 id="next-action-heading">{nextAction.label}</h2><p>{nextAction.description}</p></div>
            <dl className="focus-facts"><div><dt>已确认简历</dt><dd>{confirmedResume ? "1" : "0"}</dd></div><div><dt>保存的 JD</dt><dd>{jobs.length}</dd></div><div><dt>版本快照</dt><dd>{versions.length}</dd></div></dl>
          </section>

          <section className="dashboard-board" aria-label="最近工作记录">
            <section className="dashboard-column"><div className="section-heading"><div><p className="eyebrow">简历状态</p><h2>事实确认</h2></div><Link className="quiet-button state-link" href="/resumes">管理简历</Link></div>{resumes.length === 0 ? <DashboardEmpty href="/resumes" action="导入第一份简历" copy="还没有简历记录。系统不会把 JD 要求补写成你的经历。" /> : <div className="dashboard-list">{resumes.slice(0, 3).map((resume) => <Link className="dashboard-row" href="/resumes" key={resume.id}><span className={`status status-${resume.status === "confirmed" ? "accepted" : "pending"}`}>{resume.status === "confirmed" ? "已确认" : "待确认"}</span><strong>{resume.source_format.toUpperCase()} 简历</strong><small>{formatDate(resume.created_at)}</small></Link>)}</div>}</section>
            <section className="dashboard-column"><div className="section-heading"><div><p className="eyebrow">最近分析</p><h2>目标 JD</h2></div><Link className="quiet-button state-link" href="/jobs">新建分析</Link></div>{jobs.length === 0 ? <DashboardEmpty href="/jobs" action="粘贴目标 JD" copy="粘贴有权使用的 JD 原文后，系统会逐项寻找已确认的简历证据。" /> : <div className="dashboard-list">{jobs.slice(0, 3).map((job) => <Link className="dashboard-row" href={`/jobs/${job.id}`} key={job.id}><span className="dashboard-kind">JD</span><strong>{job.title}</strong><small>{formatDate(job.created_at)}</small></Link>)}</div>}</section>
            <section className="dashboard-column"><div className="section-heading"><div><p className="eyebrow">不可变快照</p><h2>简历版本</h2></div><Link className="quiet-button state-link" href="/history">全部记录</Link></div>{versions.length === 0 ? <DashboardEmpty href={jobs[0] ? `/jobs/${jobs[0].id}` : "/jobs"} action="完成首次版本" copy="审核建议后生成的版本不会改写主简历，也不会随着后续修改而变化。" /> : <div className="dashboard-list">{versions.slice(0, 3).map((version) => <Link className="dashboard-row" href={`/versions/${version.id}`} key={version.id}><span className="dashboard-kind">版本</span><strong>{version.job_title}</strong><small>采纳 {version.accepted_suggestion_count} 项 · {formatDate(version.created_at)}</small></Link>)}</div>}</section>
          </section>
        </>}
      </section>
    </main>
  );
}

function Step({ index, label, state }: Readonly<{ index: number; label: string; state: "done" | "active" | "next" }>) {
  return <div className={`journey-step journey-step-${state}`}><span aria-hidden="true">{index}</span><p>{label}</p></div>;
}

function DashboardEmpty({ href, action, copy }: Readonly<{ href: string; action: string; copy: string }>) {
  return <div className="dashboard-empty"><p>{copy}</p><Link href={href}>{action}</Link></div>;
}
