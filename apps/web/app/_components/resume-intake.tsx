"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { apiRequest } from "@/lib/api";

type FactStatus = "pending" | "confirmed" | "user_corrected" | "rejected";
type FactValue = { name: string } | { title: string; content: string };
type ResumeFact = {
  id: string;
  fact_type: string;
  value: FactValue;
  source_text: string;
  source_location: string;
  confidence: number;
  user_status: FactStatus;
  created_by: string;
};
type Resume = {
  id: string;
  source_format: "text" | "docx" | "pdf";
  status: "pending_confirmation" | "confirmed";
  parser_version: string;
  created_at: string;
  facts: ResumeFact[];
};
type Notice = { tone: "success" | "error" | "info"; message: string } | null;

function factTitle(fact: ResumeFact) {
  if ("name" in fact.value) return fact.value.name;
  return fact.value.title;
}

function statusText(status: FactStatus) {
  return { pending: "待确认", confirmed: "已确认", user_corrected: "已修正", rejected: "已拒绝" }[status];
}

function factTypeText(type: string) {
  return {
    skill: "技能",
    skills: "技能区段",
    project_experience: "项目经历",
    work_experience: "工作经历",
    education: "教育经历",
    summary: "自我介绍",
    contact: "基本信息",
    other: "其他内容"
  }[type] ?? type;
}

export function ResumeIntake() {
  const [resume, setResume] = useState<Resume | null>(null);
  const [inputMode, setInputMode] = useState<"text" | "file">("text");
  const [textContent, setTextContent] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [editingFact, setEditingFact] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const loadLatestResume = useCallback(async () => {
    try {
      const listResponse = await apiRequest("/api/v1/resumes");
      const profiles = (await listResponse.json()) as Array<{ id: string }>;
      if (profiles.length === 0) {
        setResume(null);
        return;
      }
      const resumeResponse = await apiRequest(`/api/v1/resumes/${profiles[0].id}`);
      setResume((await resumeResponse.json()) as Resume);
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "无法读取简历。" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadLatestResume);
  }, [loadLatestResume]);

  const pendingCount = useMemo(
    () => resume?.facts.filter((fact) => fact.user_status === "pending").length ?? 0,
    [resume]
  );

  async function importResume(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inputMode === "text" && textContent.trim().length === 0) {
      setNotice({ tone: "error", message: "请粘贴简历内容后再继续。" });
      return;
    }
    if (inputMode === "file" && selectedFile === null) {
      setNotice({ tone: "error", message: "请选择一个 PDF、DOCX 或 UTF-8 文本文件。" });
      return;
    }
    setSubmitting(true);
    setNotice(null);
    try {
      const formData = new FormData();
      if (inputMode === "text") formData.append("text_content", textContent);
      if (selectedFile !== null) formData.append("file", selectedFile);
      const response = await apiRequest("/api/v1/resumes/import", { method: "POST", body: formData }, true);
      setResume((await response.json()) as Resume);
      setEditingFact(null);
      setNotice({ tone: "success", message: "解析完成。请逐条检查下方事实，系统不会自动写入主简历。" });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "导入失败，请重试。" });
    } finally {
      setSubmitting(false);
    }
  }

  async function updateFact(fact: ResumeFact, nextStatus: Exclude<FactStatus, "pending">, value?: FactValue) {
    if (resume === null) return;
    setSubmitting(true);
    try {
      const response = await apiRequest(
        `/api/v1/resumes/${resume.id}/facts/${fact.id}`,
        { method: "PATCH", body: JSON.stringify({ user_status: nextStatus, ...(value ? { value } : {}) }) },
        true
      );
      const updated = (await response.json()) as ResumeFact;
      setResume((current) => current ? { ...current, facts: current.facts.map((item) => item.id === updated.id ? updated : item) } : current);
      setEditingFact(null);
      setNotice({ tone: "success", message: nextStatus === "confirmed" ? "事实已确认。" : nextStatus === "rejected" ? "该事实已拒绝，不会进入主简历。" : "事实已按你的输入修正。" });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "无法更新事实。" });
    } finally {
      setSubmitting(false);
    }
  }

  async function confirmResume() {
    if (resume === null) return;
    setSubmitting(true);
    try {
      const response = await apiRequest(`/api/v1/resumes/${resume.id}/confirm`, { method: "POST" }, true);
      setResume((await response.json()) as Resume);
      setNotice({ tone: "success", message: "主简历已确认。后续匹配只会使用你确认或修正过的事实。" });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "暂时无法确认主简历。" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="intake-shell">
      <header className="intake-header">
        <Link className="wordmark intake-wordmark" href="/"><span className="wordmark-mark" aria-hidden="true">R</span><span>履历校准台</span></Link>
        <Link className="quiet-button state-link" href="/">返回工作台</Link>
      </header>
      <section className="intake-intro">
        <p className="eyebrow">简历事实</p>
        <h1>先确认你说过什么，再开始优化。</h1>
        <p>原始文件只用于本次解析，完成后立即删除。每条事实都保留原文位置，只有你确认后的内容才能参与岗位匹配与导出。</p>
      </section>

      {notice ? <p className={`intake-notice intake-notice-${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>{notice.message}</p> : null}

      {loading ? <section className="intake-loading" aria-busy="true"><p className="eyebrow">正在读取</p><h2>正在恢复你的事实账本…</h2></section> : null}

      {!loading && resume === null ? (
        <section className="import-layout" aria-label="导入简历">
          <div className="import-context"><p className="eyebrow">第一步</p><h2>选择最方便的方式交给解析器。</h2><p>支持粘贴文本、DOCX、文本型 PDF 和 UTF-8 TXT。扫描版 PDF 暂不支持。</p></div>
          <form className="import-form" onSubmit={importResume}>
            <div className="mode-switch" role="tablist" aria-label="导入方式">
              <button type="button" role="tab" aria-selected={inputMode === "text"} className={inputMode === "text" ? "mode-active" : ""} onClick={() => setInputMode("text")}>粘贴文本</button>
              <button type="button" role="tab" aria-selected={inputMode === "file"} className={inputMode === "file" ? "mode-active" : ""} onClick={() => setInputMode("file")}>上传文件</button>
            </div>
            {inputMode === "text" ? <div className="form-field"><label htmlFor="resume-text">简历全文</label><textarea id="resume-text" value={textContent} onChange={(event) => setTextContent(event.target.value)} placeholder="粘贴可公开用于测试的简历文本…" rows={12} /></div> : <div className="form-field"><label htmlFor="resume-file">简历文件</label><input id="resume-file" type="file" accept=".pdf,.docx,.txt" onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)} /><small>最大 5 MB，文件会在解析后删除。</small></div>}
            <button className="primary-button import-submit" type="submit" disabled={submitting}>{submitting ? "正在解析…" : "解析并查看事实"}</button>
          </form>
        </section>
      ) : null}

      {!loading && resume !== null ? (
        <section className="fact-workspace" aria-label="审核简历事实">
          <div className="fact-summary"><div><p className="eyebrow">主简历 / {resume.status === "confirmed" ? "已确认" : "待确认"}</p><h2>{resume.status === "confirmed" ? "这份主简历已可以进入岗位匹配。" : "逐条确认，决定哪些内容可以被引用。"}</h2></div><dl><div><dt>事实总数</dt><dd>{resume.facts.length}</dd></div><div><dt>待确认</dt><dd>{pendingCount}</dd></div><div><dt>来源格式</dt><dd>{resume.source_format.toUpperCase()}</dd></div></dl></div>
          <div className="fact-actions"><button className="quiet-button" type="button" onClick={() => { setResume(null); setTextContent(""); setSelectedFile(null); setNotice(null); }}>导入另一份简历</button><button className="primary-button" type="button" disabled={pendingCount > 0 || resume.status === "confirmed" || submitting} onClick={confirmResume}>{resume.status === "confirmed" ? "主简历已确认" : pendingCount > 0 ? `还需审核 ${pendingCount} 条` : "确认主简历"}</button></div>
          <div className="fact-list">
            {resume.facts.map((fact, index) => <FactRow key={fact.id} fact={fact} index={index} isEditing={editingFact === fact.id} disabled={submitting || resume.status === "confirmed"} onEdit={() => setEditingFact(fact.id)} onCancel={() => setEditingFact(null)} onUpdate={updateFact} />)}
          </div>
        </section>
      ) : null}
    </main>
  );
}

function FactRow({ fact, index, isEditing, disabled, onEdit, onCancel, onUpdate }: Readonly<{ fact: ResumeFact; index: number; isEditing: boolean; disabled: boolean; onEdit: () => void; onCancel: () => void; onUpdate: (fact: ResumeFact, status: Exclude<FactStatus, "pending">, value?: FactValue) => Promise<void> }>) {
  const [draft, setDraft] = useState(factTitle(fact));
  const [content, setContent] = useState("content" in fact.value ? fact.value.content : "");
  const isSkill = "name" in fact.value;
  return <article className="fact-row"><div className="fact-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</div><div className="fact-body"><div className="fact-heading"><div><p>{factTypeText(fact.fact_type)}</p><h3>{factTitle(fact)}</h3></div><span className={`status status-${fact.user_status}`}>{statusText(fact.user_status)}</span></div>{isEditing ? <div className="fact-editor"><label htmlFor={`fact-${fact.id}`}>{isSkill ? "技能名称" : "区段标题"}</label><input id={`fact-${fact.id}`} value={draft} onChange={(event) => setDraft(event.target.value)} />{!isSkill ? <><label htmlFor={`content-${fact.id}`}>区段内容</label><textarea id={`content-${fact.id}`} value={content} onChange={(event) => setContent(event.target.value)} rows={5} /></> : null}<div className="fact-row-actions"><button className="secondary-button" type="button" onClick={onCancel}>取消</button><button className="primary-button" type="button" onClick={() => onUpdate(fact, "user_corrected", isSkill ? { name: draft } : { title: draft, content })}>保存修正</button></div></div> : <><p className="fact-source">{fact.source_text}</p><p className="fact-location">来源：{fact.source_location}</p><div className="fact-row-actions"><button className="quiet-button" type="button" disabled={disabled} onClick={onEdit}>修正</button><button className="secondary-button" type="button" disabled={disabled} onClick={() => onUpdate(fact, "rejected")}>拒绝</button><button className="primary-button" type="button" disabled={disabled} onClick={() => onUpdate(fact, "confirmed")}>确认事实</button></div></>}</div></article>;
}
