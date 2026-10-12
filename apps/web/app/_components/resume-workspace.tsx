"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

import SpotlightCard from "./SpotlightCard/SpotlightCard";

type Decision = "pending" | "accepted" | "rejected";

type Suggestion = {
  id: string;
  heading: string;
  section: string;
  before: string;
  after: string;
  reason: string;
  resumeEvidence: string;
  jdEvidence: string;
  decision: Decision;
};

const initialSuggestions: Suggestion[] = [
  {
    id: "project-order",
    heading: "将性能优化项目置于项目经历首位",
    section: "项目经历 · 顺序调整",
    before: "按原简历顺序呈现三个项目。",
    after: "将“交易链路性能优化”调整至首位，内容不变。",
    reason: "该项目与岗位的高并发服务职责关联最直接。",
    resumeEvidence: "简历第 2 页 · 交易链路性能优化项目",
    jdEvidence: "JD 职责 · 建设稳定、高性能的后端服务",
    decision: "pending"
  },
  {
    id: "skill-order",
    heading: "在技能栏优先呈现 Python 与 PostgreSQL",
    section: "专业技能 · 顺序调整",
    before: "Python、Docker、PostgreSQL、Linux 按原顺序排列。",
    after: "Python、PostgreSQL、Docker、Linux，技能内容不变。",
    reason: "JD 将 Python 与 PostgreSQL 列为硬性技术栈。",
    resumeEvidence: "简历第 1 页 · 专业技能",
    jdEvidence: "JD 任职要求 · 熟悉 Python、PostgreSQL",
    decision: "pending"
  },
  {
    id: "missing-kafka",
    heading: "Kafka 仅作为能力缺口展示",
    section: "技术栈 · 不写入简历",
    before: "简历未出现 Kafka 相关证据。",
    after: "不添加 Kafka 能力表述，仅保留“当前简历无证据”。",
    reason: "岗位提及 Kafka，但系统不能将 JD 要求推断为你的经验。",
    resumeEvidence: "当前已确认事实中无对应条目",
    jdEvidence: "JD 加分项 · 有 Kafka 等消息队列经验",
    decision: "pending"
  }
];

const navigation = ["工作台", "简历事实", "目标 JD", "优化中心"];
const navigationLinks: Partial<Record<(typeof navigation)[number], string>> = {
  "简历事实": "/resumes",
  "目标 JD": "/jobs",
  "优化中心": "/jobs"
};
const steps = ["导入简历", "确认事实", "解析 JD", "审核修改", "导出版本"];

function statusLabel(decision: Decision) {
  if (decision === "accepted") return "已采纳";
  if (decision === "rejected") return "已跳过";
  return "待审核";
}

export function ResumeWorkspace() {
  const [activeNavigation, setActiveNavigation] = useState("工作台");
  const [suggestions, setSuggestions] = useState(initialSuggestions);
  const [selectedId, setSelectedId] = useState(initialSuggestions[0].id);
  const [notice, setNotice] = useState("已加载合成演示数据，不包含真实简历内容。");
  const [showEvidence, setShowEvidence] = useState(true);

  const selected = useMemo(
    () => suggestions.find((suggestion) => suggestion.id === selectedId) ?? suggestions[0],
    [selectedId, suggestions]
  );
  const pendingCount = suggestions.filter((suggestion) => suggestion.decision === "pending").length;
  const acceptedCount = suggestions.filter((suggestion) => suggestion.decision === "accepted").length;

  function decide(decision: Exclude<Decision, "pending">) {
    setSuggestions((current) =>
      current.map((suggestion) =>
        suggestion.id === selected.id ? { ...suggestion, decision } : suggestion
      )
    );
    setNotice(
      decision === "accepted"
        ? `已采纳“${selected.heading}”。这只是本地演示，尚未写入简历版本。`
        : `已跳过“${selected.heading}”。原始简历内容保持不变。`
    );
  }

  return (
    <main className="workspace-shell">
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {notice}
      </p>

      <aside className="workspace-sidebar" aria-label="主导航">
        <a className="wordmark" href="#workspace" aria-label="履历校准台首页">
          <span className="wordmark-mark" aria-hidden="true">R</span>
          <span>履历校准台</span>
        </a>

        <div className="workspace-switcher">
          <span className="eyebrow">当前工作区</span>
          <strong>后端工程师求职</strong>
          <span className="workspace-date">最近编辑 · 今天 10:42</span>
        </div>

        <nav className="main-navigation">
          {navigation.map((item) => navigationLinks[item] ? (
            <Link className="nav-item" key={item} href={navigationLinks[item]}><span>{item}</span></Link>
          ) : (
            <button
              className={activeNavigation === item ? "nav-item nav-item-active" : "nav-item"}
              key={item}
              type="button"
              aria-current={activeNavigation === item ? "page" : undefined}
              onClick={() => {
                setActiveNavigation(item);
                setNotice(`已切换至${item}。首版界面会在对应功能接入后展示真实数据。`);
              }}
            >
              <span>{item}</span>
              {item === "优化中心" && pendingCount > 0 ? <b>{pendingCount}</b> : null}
            </button>
          ))}
        </nav>

        <div className="sidebar-footnote">
          <span className="privacy-pulse" aria-hidden="true" />
          <p>只有已确认的事实才能进入导出版本。</p>
        </div>
      </aside>

      <section className="workspace-main" id="workspace" tabIndex={-1}>
        <header className="workspace-header">
          <div>
            <p className="eyebrow">{activeNavigation} / 示例工作区</p>
            <h1>把真实经历，校准成岗位能读懂的证据。</h1>
          </div>
          <div className="header-actions">
            <Link className="quiet-button state-link" href="/login">登录</Link>
            <button className="quiet-button" type="button" onClick={() => setShowEvidence((value) => !value)}>
              {showEvidence ? "收起证据轨" : "展开证据轨"}
            </button>
            <button
              className="primary-button"
              type="button"
              onClick={() => setNotice("导出将在全部建议审核后开放。当前为交互演示，不会生成文件。")}
            >
              查看可导出版本
            </button>
          </div>
        </header>

        <section className="journey" aria-label="简历优化流程">
          {steps.map((step, index) => {
            const state = index < 3 ? "done" : index === 3 ? "active" : "next";
            return (
              <div className={`journey-step journey-step-${state}`} key={step}>
                <span aria-hidden="true">{index + 1}</span>
                <p>{step}</p>
              </div>
            );
          })}
        </section>

        <section className="focus-band" aria-labelledby="focus-heading">
          <div>
            <p className="eyebrow">本次校准对象</p>
            <h2 id="focus-heading">Python 后端工程师</h2>
            <p>杭州 · 全职 · 用户粘贴 JD</p>
          </div>
          <dl className="focus-facts">
            <div>
              <dt>已确认事实</dt>
              <dd>18 条</dd>
            </div>
            <div>
              <dt>JD 要求</dt>
              <dd>12 项</dd>
            </div>
            <div>
              <dt>待你决定</dt>
              <dd>{pendingCount} 项</dd>
            </div>
          </dl>
        </section>

        <section className="decision-layout" aria-label="修改建议与证据">
          <div className="suggestion-list">
            <div className="section-heading">
              <div>
                <p className="eyebrow">逐项审核</p>
                <h2>每一次调整，都留在你的掌控里。</h2>
              </div>
              <span className="count-label">已采纳 {acceptedCount} 项</span>
            </div>

            {suggestions.map((suggestion, index) => (
              <button
                className={selected.id === suggestion.id ? "suggestion-row suggestion-row-selected" : "suggestion-row"}
                key={suggestion.id}
                type="button"
                aria-pressed={selected.id === suggestion.id}
                onClick={() => {
                  setSelectedId(suggestion.id);
                  setNotice(`正在查看第 ${index + 1} 条建议的原文与证据。`);
                }}
              >
                <span className="suggestion-index" aria-hidden="true">0{index + 1}</span>
                <span className="suggestion-copy">
                  <strong>{suggestion.heading}</strong>
                  <small>{suggestion.section}</small>
                </span>
                <span className={`status status-${suggestion.decision}`}>{statusLabel(suggestion.decision)}</span>
              </button>
            ))}
          </div>

          {showEvidence ? (
            <SpotlightCard className="signal-card" spotlightColor="rgba(13, 148, 136, 0.18)">
              <div className="signal-card-inner">
                <div className="detail-topline">
                  <p className="eyebrow">建议详情</p>
                  <span className={`status status-${selected.decision}`}>{statusLabel(selected.decision)}</span>
                </div>
                <h2>{selected.heading}</h2>

                <div className="diff-panel" aria-label="修改前后对比">
                  <div>
                    <span>原文</span>
                    <p>{selected.before}</p>
                  </div>
                  <div>
                    <span>建议</span>
                    <p>{selected.after}</p>
                  </div>
                </div>

                <p className="detail-reason">{selected.reason}</p>

                <div className="evidence-stack">
                  <div className="evidence-item">
                    <span>简历依据</span>
                    <strong>{selected.resumeEvidence}</strong>
                  </div>
                  <div className="evidence-item">
                    <span>JD 依据</span>
                    <strong>{selected.jdEvidence}</strong>
                  </div>
                </div>

                <div className="decision-actions">
                  <button className="secondary-button" type="button" onClick={() => decide("rejected")}>
                    跳过建议
                  </button>
                  <button className="primary-button" type="button" onClick={() => decide("accepted")}>
                    采纳此建议
                  </button>
                </div>
              </div>
            </SpotlightCard>
          ) : null}
        </section>

        <footer className="trust-note">
          <span className="trust-rule" aria-hidden="true" />
          <p>
            系统只重排、润色或组合已确认事实。JD 中未被简历证实的要求会展示为信息缺口，不会写进你的简历。
          </p>
        </footer>
      </section>
    </main>
  );
}
