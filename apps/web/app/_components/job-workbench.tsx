"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { apiRequest } from "@/lib/api";

type ResumeSummary = { id: string; status: "pending_confirmation" | "confirmed" };
type JobRequirement = {
  id: string;
  requirement_type: "required" | "bonus";
  value: { name: string };
  source_text: string;
  source_location: string;
};
type Job = { id: string; title: string; requirements: JobRequirement[] };
type MatchItem = {
  job_requirement_id: string;
  technology: string;
  requirement_type: "required" | "bonus";
  job_source_text: string;
  result: "satisfied" | "no_evidence";
  resume_fact_id: string | null;
  resume_source_text: string | null;
};
type Match = {
  id: string;
  resume_profile_id: string;
  job_description_id: string;
  algorithm_version: string;
  created_at: string;
  satisfied: MatchItem[];
  no_evidence: MatchItem[];
};
type Suggestion = {
  id: string;
  section: "skills";
  original_text: string;
  proposed_text: string;
  change_type: "reorder";
  reason: string;
  resume_fact_ids: string[];
  job_requirement_ids: string[];
  risk: "low";
  requires_user_confirmation: true;
  user_decision: "pending" | "accepted" | "rejected";
};
type ResumeVersion = {
  id: string;
  content: { job_title: string; sections: Array<{ resume_fact_id: string; fact_type: string; source_text: string; source_location: string }> };
  accepted_suggestion_ids: string[];
};
type DocumentExport = { download_url: string; expires_at: string };
type Notice = { tone: "success" | "error" | "info"; message: string } | null;

function decisionLabel(decision: Suggestion["user_decision"]) {
  return { pending: "待你决定", accepted: "已采纳", rejected: "已跳过" }[decision];
}

function sectionLabel(type: string) {
  return { skills: "专业技能", project_experience: "项目经历", work_experience: "工作经历", education: "教育经历", summary: "自我介绍", contact: "基本信息", other: "其他内容" }[type] ?? type;
}

export function JobWorkbench({ jobId }: Readonly<{ jobId?: string }>) {
  const [resumeId, setResumeId] = useState<string | null>(null);
  const [loadingResume, setLoadingResume] = useState(true);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [match, setMatch] = useState<Match | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [version, setVersion] = useState<ResumeVersion | null>(null);
  const [creatingVersion, setCreatingVersion] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportExpiresAt, setExportExpiresAt] = useState<string | null>(null);
  const [versionIdempotencyKey, setVersionIdempotencyKey] = useState<string | null>(null);

  const loadConfirmedResume = useCallback(async () => {
    try {
      const response = await apiRequest("/api/v1/resumes");
      const resumes = (await response.json()) as ResumeSummary[];
      setResumeId(resumes.find((resume) => resume.status === "confirmed")?.id ?? null);
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "无法读取主简历。" });
    } finally {
      setLoadingResume(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadConfirmedResume);
  }, [loadConfirmedResume]);

  const loadStoredJob = useCallback(async () => {
    if (jobId === undefined) return;
    try {
      const jobResponse = await apiRequest(`/api/v1/jobs/${jobId}`);
      const storedJob = (await jobResponse.json()) as Job;
      const matchResponse = await apiRequest(`/api/v1/jobs/${storedJob.id}/matches`);
      const storedMatches = (await matchResponse.json()) as Match[];
      setJob(storedJob);
      if (storedMatches.length === 0) {
        setMatch(null);
        setSuggestions([]);
        setNotice({ tone: "info", message: "这个历史 JD 尚未保存匹配快照。你可以用当前已确认的主简历重新分析一次。" });
        return;
      }
      const storedMatch = storedMatches[0];
      const suggestionsResponse = await apiRequest(
        `/api/v1/optimizations?resume_profile_id=${storedMatch.resume_profile_id}&job_description_id=${storedJob.id}`
      );
      setMatch(storedMatch);
      setSuggestions((await suggestionsResponse.json()) as Suggestion[]);
      setNotice({ tone: "info", message: "已恢复保存的 JD、匹配证据和对应的简历快照。" });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "无法恢复该 JD。" });
    }
  }, [jobId]);

  useEffect(() => {
    if (jobId !== undefined) void Promise.resolve().then(loadStoredJob);
  }, [jobId, loadStoredJob]);

  const requiredRequirements = useMemo(
    () => job?.requirements.filter((requirement) => requirement.requirement_type === "required") ?? [],
    [job]
  );
  const bonusRequirements = useMemo(
    () => job?.requirements.filter((requirement) => requirement.requirement_type === "bonus") ?? [],
    [job]
  );
  const pendingSuggestions = suggestions.filter((suggestion) => suggestion.user_decision === "pending").length;

  async function analyseJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (resumeId === null) return;
    if (title.trim().length === 0) {
      setFormError("请填写岗位名称，便于之后生成针对该岗位的简历版本。");
      return;
    }
    if (content.trim().length < 80) {
      setFormError("JD 至少需要 80 个字符，才能提取足够的岗位要求。");
      return;
    }

    setSubmitting(true);
    setFormError(null);
    setNotice(null);
    setJob(null);
    setMatch(null);
    setSuggestions([]);
    setVersion(null);
    setExportExpiresAt(null);
    setVersionIdempotencyKey(null);
    try {
      const jobResponse = await apiRequest(
        "/api/v1/jobs/from-text",
        { method: "POST", body: JSON.stringify({ title: title.trim(), content: content.trim() }) },
        true
      );
      const createdJob = (await jobResponse.json()) as Job;
      const [matchResponse, suggestionsResponse] = await Promise.all([
        apiRequest(
          "/api/v1/matches",
          { method: "POST", body: JSON.stringify({ resume_profile_id: resumeId, job_description_id: createdJob.id }) },
          true
        ),
        apiRequest(
          "/api/v1/optimizations",
          { method: "POST", body: JSON.stringify({ resume_profile_id: resumeId, job_description_id: createdJob.id }) },
          true
        )
      ]);
      setJob(createdJob);
      setMatch((await matchResponse.json()) as Match);
      setSuggestions((await suggestionsResponse.json()) as Suggestion[]);
      window.history.replaceState(null, "", `/jobs/${createdJob.id}`);
      setNotice({ tone: "success", message: "JD 已解析。以下结论仅引用已确认的简历事实。" });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "JD 暂时无法分析，请检查后重试。" });
    } finally {
      setSubmitting(false);
    }
  }

  async function analyseStoredJob() {
    if (resumeId === null || job === null) return;
    setSubmitting(true);
    setNotice(null);
    setVersion(null);
    setExportExpiresAt(null);
    setVersionIdempotencyKey(null);
    try {
      const [matchResponse, suggestionsResponse] = await Promise.all([
        apiRequest(
          "/api/v1/matches",
          { method: "POST", body: JSON.stringify({ resume_profile_id: resumeId, job_description_id: job.id }) },
          true
        ),
        apiRequest(
          "/api/v1/optimizations",
          { method: "POST", body: JSON.stringify({ resume_profile_id: resumeId, job_description_id: job.id }) },
          true
        )
      ]);
      setMatch((await matchResponse.json()) as Match);
      setSuggestions((await suggestionsResponse.json()) as Suggestion[]);
      setNotice({ tone: "success", message: "已按当前已确认主简历保存一份新的匹配快照。" });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "无法重新分析该 JD。" });
    } finally {
      setSubmitting(false);
    }
  }

  async function decideSuggestion(suggestion: Suggestion, decision: "accepted" | "rejected") {
    setDecidingId(suggestion.id);
    try {
      const response = await apiRequest(
        `/api/v1/optimizations/${suggestion.id}`,
        { method: "PATCH", body: JSON.stringify({ user_decision: decision }) },
        true
      );
      const updated = (await response.json()) as Suggestion;
      setSuggestions((current) => current.map((item) => item.id === updated.id ? updated : item));
      setNotice({ tone: "success", message: decision === "accepted" ? "建议已采纳，原始主简历尚未被直接改写。" : "建议已跳过，原始主简历保持不变。" });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "无法保存你的决定，请重试。" });
    } finally {
      setDecidingId(null);
    }
  }

  async function createVersion() {
    if (match === null || job === null || pendingSuggestions > 0) return;
    const idempotencyKey = versionIdempotencyKey ?? crypto.randomUUID();
    setVersionIdempotencyKey(idempotencyKey);
    setCreatingVersion(true);
    try {
      const response = await apiRequest(
        "/api/v1/resume-versions",
        { method: "POST", body: JSON.stringify({ resume_profile_id: match.resume_profile_id, job_description_id: job.id, idempotency_key: idempotencyKey }) },
        true
      );
      setVersion((await response.json()) as ResumeVersion);
      setExportExpiresAt(null);
      setNotice({ tone: "success", message: "岗位专属简历版本已生成。它是不可变快照，主简历不会被改写。" });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "暂时无法生成简历版本，请重试。" });
    } finally {
      setCreatingVersion(false);
    }
  }

  async function downloadDocx() {
    if (version === null) return;
    setExporting(true);
    try {
      const exportResponse = await apiRequest(`/api/v1/resume-versions/${version.id}/exports/docx`, { method: "POST" }, true);
      const exportInfo = (await exportResponse.json()) as DocumentExport;
      const fileResponse = await apiRequest(exportInfo.download_url);
      const fileUrl = URL.createObjectURL(await fileResponse.blob());
      const anchor = document.createElement("a");
      anchor.href = fileUrl;
      anchor.download = "targeted-resume.docx";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(fileUrl);
      setExportExpiresAt(exportInfo.expires_at);
      setNotice({ tone: "success", message: "DOCX 已开始下载。服务器中的临时导出文件将在 24 小时后清理。" });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "DOCX 导出失败，请重试。" });
    } finally {
      setExporting(false);
    }
  }

  return (
    <main className="job-shell">
      <header className="intake-header">
        <Link className="wordmark intake-wordmark" href="/"><span className="wordmark-mark" aria-hidden="true">R</span><span>履历校准台</span></Link>
        <div className="job-header-actions"><Link className="quiet-button state-link" href="/resumes">简历事实</Link><Link className="quiet-button state-link" href="/history">历史记录</Link><Link className="quiet-button state-link" href="/">返回工作台</Link></div>
      </header>

      <section className="job-intro">
        <p className="eyebrow">目标 JD</p>
        <h1>让岗位要求，逐项回到你的真实证据。</h1>
        <p>系统只将已确认事实与 JD 原文对应。未找到证据只表示当前简历没有提供依据，不代表你不具备该能力。</p>
      </section>

      {notice ? <p className={`intake-notice intake-notice-${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>{notice.message}</p> : null}

      {loadingResume ? <section className="intake-loading" aria-busy="true"><p className="eyebrow">正在读取</p><h2>正在确认可用于匹配的主简历…</h2></section> : null}

      {!loadingResume && resumeId === null ? (
        <section className="job-empty-state">
          <p className="eyebrow">需要先完成上一步</p>
          <h2>还没有已确认的主简历。</h2>
          <p>请先导入简历，并逐条确认或修正其中的事实。系统不会用待确认内容进行岗位匹配。</p>
          <Link className="primary-button state-link" href="/resumes">去确认简历事实</Link>
        </section>
      ) : null}

      {!loadingResume && resumeId !== null ? (
        <>
          <form className="job-form" onSubmit={analyseJob} noValidate>
            <div className="job-form-intro"><p className="eyebrow">粘贴岗位描述</p><h2>从原文中提取要求，不猜测职位含义。</h2><p>岗位名称用于后续版本标识，JD 正文至少 80 个字符。</p></div>
            <div className="job-form-fields">
              {formError ? <p className="form-status form-status-error" role="alert">{formError}</p> : null}
              <div className="form-field"><label htmlFor="job-title">岗位名称</label><input id="job-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：Python 后端工程师" maxLength={200} /></div>
              <div className="form-field"><label htmlFor="job-content">JD 正文</label><textarea id="job-content" value={content} onChange={(event) => setContent(event.target.value)} placeholder="粘贴你有权使用的岗位描述原文…" rows={12} aria-describedby="job-content-help" /><small id="job-content-help">将保留这份 JD 用于解释匹配与生成该岗位的简历版本。</small></div>
              <button className="primary-button job-submit" type="submit" disabled={submitting}>{submitting ? "正在提取证据…" : "解析 JD 并查看证据"}</button>
            </div>
          </form>

          {job !== null && match === null ? <section className="job-snapshot-missing"><div><p className="eyebrow">历史记录</p><h2>这份 JD 还没有匹配快照。</h2><p>首次分析发生在快照功能上线前。重新分析会绑定当前已确认的主简历，不会改动该 JD 原文。</p></div><button className="secondary-button" type="button" disabled={submitting} onClick={analyseStoredJob}>{submitting ? "正在保存快照…" : "按当前主简历重新分析"}</button></section> : null}

          {job !== null && match !== null ? <section className="job-results" aria-label="JD 匹配结果">
            <div className="job-result-summary"><div><p className="eyebrow">匹配证据 / {job.title}</p><h2>每一项结论，都能回到对应原文。</h2></div><dl><div><dt>硬性要求</dt><dd>{requiredRequirements.length}</dd></div><div><dt>已有证据</dt><dd>{match.satisfied.length}</dd></div><div><dt>当前无证据</dt><dd>{match.no_evidence.length}</dd></div></dl></div>

            <div className="match-columns">
              <RequirementList title="岗位要求" eyebrow="JD 原文" requirements={requiredRequirements} emptyText="未识别出硬性技术要求。" />
              <RequirementList title="加分项" eyebrow="JD 原文" requirements={bonusRequirements} emptyText="未识别出加分技术项。" />
            </div>

            <div className="evidence-layout">
              <MatchList title="已有简历证据" eyebrow="已确认事实" items={match.satisfied} kind="satisfied" />
              <MatchList title="当前无证据" eyebrow="保持诚实" items={match.no_evidence} kind="no_evidence" />
            </div>

            <section className="suggestion-review" aria-labelledby="suggestion-heading">
              <div className="section-heading"><div><p className="eyebrow">逐项审批</p><h2 id="suggestion-heading">只建议不改变事实的调整。</h2></div><span className="count-label">待你决定 {pendingSuggestions} 项</span></div>
              {suggestions.length === 0 ? <p className="review-empty">当前没有可安全生成的修改建议。系统不会为了提高匹配感而补写技能、经历或数字。</p> : <div className="review-list">{suggestions.map((suggestion, index) => <SuggestionReview key={suggestion.id} suggestion={suggestion} index={index} busy={decidingId === suggestion.id} onDecide={decideSuggestion} />)}</div>}
            </section>

            <section className="version-panel" aria-labelledby="version-heading">
              <div><p className="eyebrow">生成版本</p><h2 id="version-heading">把已审核的选择，冻结成一份可导出的快照。</h2><p>只包含已确认或你修正过的区段。已接受建议仅影响呈现顺序，主简历保持原样。</p></div>
              {pendingSuggestions > 0 ? <p className="version-wait">还有 {pendingSuggestions} 项建议待审核。完成选择后才可生成版本。</p> : version === null ? <button className="primary-button" type="button" disabled={creatingVersion} onClick={createVersion}>{creatingVersion ? "正在生成版本…" : "生成岗位专属版本"}</button> : <div className="version-ready"><p>已冻结 {version.content.sections.length} 个区段，采纳 {version.accepted_suggestion_ids.length} 项建议。</p><button className="primary-button" type="button" disabled={exporting} onClick={downloadDocx}>{exporting ? "正在准备 DOCX…" : "下载 DOCX"}</button>{exportExpiresAt ? <small>本次临时下载文件有效至 {new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Shanghai" }).format(new Date(exportExpiresAt))}</small> : null}</div>}
              {version !== null ? <div className="version-preview"><p className="eyebrow">版本内容预览</p>{version.content.sections.map((section) => <article key={section.resume_fact_id}><strong>{sectionLabel(section.fact_type)}</strong><p>{section.source_text}</p><small>{section.source_location}</small></article>)}<Link className="quiet-button state-link version-history-link" href={`/versions/${version.id}`}>打开版本详情</Link></div> : null}
            </section>
          </section> : null}
        </>
      ) : null}
    </main>
  );
}

function RequirementList({ title, eyebrow, requirements, emptyText }: Readonly<{ title: string; eyebrow: string; requirements: JobRequirement[]; emptyText: string }>) {
  return <section className="requirement-list"><p className="eyebrow">{eyebrow}</p><h2>{title}</h2>{requirements.length === 0 ? <p className="list-empty">{emptyText}</p> : requirements.map((requirement) => <article className="requirement-row" key={requirement.id}><strong>{requirement.value.name}</strong><p>{requirement.source_text}</p><small>{requirement.source_location}</small></article>)}</section>;
}

function MatchList({ title, eyebrow, items, kind }: Readonly<{ title: string; eyebrow: string; items: MatchItem[]; kind: MatchItem["result"] }>) {
  const emptyText = kind === "satisfied" ? "暂未找到已确认的对应事实。" : "所有已识别要求均已找到简历证据。";
  return <section className={`match-list match-list-${kind}`}><p className="eyebrow">{eyebrow}</p><h2>{title}</h2>{items.length === 0 ? <p className="list-empty">{emptyText}</p> : items.map((item) => <article className="match-row" key={item.job_requirement_id}><div><strong>{item.technology}</strong><span>{item.requirement_type === "required" ? "硬性要求" : "加分项"}</span></div><p><b>JD：</b>{item.job_source_text}</p>{kind === "satisfied" ? <p><b>简历：</b>{item.resume_source_text}</p> : <p className="no-evidence-copy">当前简历未提供证据，不代表你不具备该能力。</p>}</article>)}</section>;
}

function SuggestionReview({ suggestion, index, busy, onDecide }: Readonly<{ suggestion: Suggestion; index: number; busy: boolean; onDecide: (suggestion: Suggestion, decision: "accepted" | "rejected") => Promise<void> }>) {
  const decided = suggestion.user_decision !== "pending";
  return <article className="review-row"><div className="review-index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</div><div className="review-content"><div className="review-heading"><div><p>{suggestion.section === "skills" ? "技能区段 · 顺序调整" : suggestion.section}</p><h3>将已确认的相关技能更靠前呈现</h3></div><span className={`status status-${suggestion.user_decision}`}>{decisionLabel(suggestion.user_decision)}</span></div><div className="review-diff"><div><span>原文</span><p>{suggestion.original_text}</p></div><div><span>建议</span><p>{suggestion.proposed_text}</p></div></div><p className="review-reason">{suggestion.reason}</p><p className="review-evidence">关联 {suggestion.resume_fact_ids.length} 条简历事实与 {suggestion.job_requirement_ids.length} 条 JD 要求，风险等级：低。</p>{!decided ? <div className="fact-row-actions"><button className="secondary-button" type="button" disabled={busy} onClick={() => onDecide(suggestion, "rejected")}>跳过建议</button><button className="primary-button" type="button" disabled={busy} onClick={() => onDecide(suggestion, "accepted")}>{busy ? "正在保存…" : "采纳此建议"}</button></div> : null}</div></article>;
}
