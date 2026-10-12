"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { apiRequest } from "@/lib/api";

type ResumeVersion = { id: string; content: { job_title: string; sections: Array<{ resume_fact_id: string; fact_type: string; source_text: string; source_location: string }> }; accepted_suggestion_ids: string[] };
type DocumentExport = { download_url: string; expires_at: string };
type Notice = { tone: "success" | "error"; message: string } | null;

function sectionLabel(type: string) {
  return { skills: "专业技能", project_experience: "项目经历", work_experience: "工作经历", education: "教育经历", summary: "自我介绍", contact: "基本信息", other: "其他内容" }[type] ?? type;
}

export function VersionViewer({ versionId }: Readonly<{ versionId: string }>) {
  const [version, setVersion] = useState<ResumeVersion | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  const loadVersion = useCallback(async () => {
    try {
      const response = await apiRequest(`/api/v1/resume-versions/${versionId}`);
      setVersion((await response.json()) as ResumeVersion);
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "无法读取该简历版本。" });
    } finally {
      setLoading(false);
    }
  }, [versionId]);

  useEffect(() => {
    void Promise.resolve().then(loadVersion);
  }, [loadVersion]);

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
      setNotice({ tone: "success", message: "DOCX 已开始下载。服务器中的临时导出文件将在 24 小时后清理。" });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "DOCX 导出失败，请重试。" });
    } finally {
      setExporting(false);
    }
  }

  return <main className="history-shell">
    <header className="intake-header"><Link className="wordmark intake-wordmark" href="/"><span className="wordmark-mark" aria-hidden="true">R</span><span>履历校准台</span></Link><Link className="quiet-button state-link" href="/history">返回历史记录</Link></header>
    {notice ? <p className={`intake-notice intake-notice-${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>{notice.message}</p> : null}
    {loading ? <section className="intake-loading" aria-busy="true"><p className="eyebrow">正在读取</p><h2>正在恢复不可变简历快照…</h2></section> : null}
    {!loading && version !== null ? <section className="version-detail"><div className="version-detail-heading"><div><p className="eyebrow">岗位专属版本</p><h1>{version.content.job_title}</h1><p>已冻结 {version.content.sections.length} 个区段，采纳 {version.accepted_suggestion_ids.length} 项建议。</p></div><button className="primary-button" type="button" disabled={exporting} onClick={downloadDocx}>{exporting ? "正在准备 DOCX…" : "下载 DOCX"}</button></div><div className="version-preview">{version.content.sections.map((section) => <article key={section.resume_fact_id}><strong>{sectionLabel(section.fact_type)}</strong><p>{section.source_text}</p><small>{section.source_location}</small></article>)}</div></section> : null}
  </main>;
}
