"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState, useSyncExternalStore } from "react";

import { apiRequest as request } from "@/lib/api";

type FormStatus = { tone: "success" | "error"; message: string } | null;
type AuthFrameProps = Readonly<{
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}>;
type StatusMessageProps = Readonly<{ status: FormStatus }>;

async function apiRequest(path: string, body: Record<string, unknown>, csrf = false) {
  return request(path, {
    method: "POST",
    body: JSON.stringify(body)
  }, csrf);
}

function useHashToken() {
  const hash = useSyncExternalStore(
    (onChange) => {
      window.addEventListener("hashchange", onChange);
      return () => window.removeEventListener("hashchange", onChange);
    },
    () => window.location.hash,
    () => ""
  );
  return new URLSearchParams(hash.slice(1)).get("token");
}

function AuthFrame({
  eyebrow,
  title,
  description,
  children
}: AuthFrameProps) {
  return (
    <main className="auth-shell">
      <section className="auth-context">
        <Link className="wordmark auth-wordmark" href="/">
          <span className="wordmark-mark" aria-hidden="true">R</span>
          <span>履历校准台</span>
        </Link>
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <p className="auth-principle">只使用已确认事实，绝不替你虚构经历或自动投递。</p>
      </section>
      <section className="auth-panel">{children}</section>
    </main>
  );
}

function StatusMessage({ status }: StatusMessageProps) {
  if (status === null) return null;
  return (
    <p className={`form-status form-status-${status.tone}`} role={status.tone === "error" ? "alert" : "status"}>
      {status.message}
    </p>
  );
}

function PasswordField({
  id,
  label,
  autoComplete,
  value,
  onChange
}: Readonly<{
  id: string;
  label: string;
  autoComplete: string;
  value: string;
  onChange: (value: string) => void;
}>) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="form-field">
      <label htmlFor={id}>{label}</label>
      <div className="password-input">
        <input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          minLength={12}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          required
        />
        <button type="button" className="password-toggle" onClick={() => setVisible((current) => !current)}>
          {visible ? "隐藏" : "显示"}
        </button>
      </div>
    </div>
  );
}

export function RegisterForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invitationCode, setInvitationCode] = useState("");
  const [isAdult, setIsAdult] = useState(false);
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState<FormStatus>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setStatus(null);
    try {
      await apiRequest("/api/v1/auth/register", {
        email,
        password,
        invitation_code: invitationCode,
        is_adult: isAdult
      });
      setStatus({ tone: "success", message: "账号已创建，请查收邮箱验证邮件。" });
    } catch (error) {
      setStatus({ tone: "error", message: error instanceof Error ? error.message : "注册失败，请重试。" });
    } finally {
      setPending(false);
    }
  }

  async function resend() {
    setPending(true);
    try {
      await apiRequest("/api/v1/auth/email-verification/request", {}, true);
      setStatus({ tone: "success", message: "如邮箱尚未验证，新的验证邮件已发送。" });
    } catch (error) {
      setStatus({ tone: "error", message: error instanceof Error ? error.message : "暂时无法重新发送。" });
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthFrame eyebrow="受邀注册" title="先建立一份可信的能力档案。" description="验证邮箱后，你可以保存自己的主简历和岗位版本。">
      <form className="auth-form" onSubmit={submit}>
        <div className="form-field">
          <label htmlFor="register-email">邮箱</label>
          <input id="register-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </div>
        <PasswordField id="register-password" label="密码" autoComplete="new-password" value={password} onChange={setPassword} />
        <div className="form-field">
          <label htmlFor="invitation-code">邀请码</label>
          <input id="invitation-code" autoComplete="off" value={invitationCode} onChange={(event) => setInvitationCode(event.target.value)} required />
        </div>
        <label className="consent-field">
          <input type="checkbox" checked={isAdult} onChange={(event) => setIsAdult(event.target.checked)} required />
          <span>我已年满 18 周岁，并理解简历内容必须真实。</span>
        </label>
        <StatusMessage status={status} />
        <button className="primary-button auth-submit" type="submit" disabled={pending}>{pending ? "正在创建…" : "创建账号"}</button>
        {status?.tone === "success" ? <button className="quiet-button auth-resend" type="button" onClick={resend} disabled={pending}>重新发送验证邮件</button> : null}
      </form>
      <p className="auth-switch">已有账号？<Link href="/login">登录</Link></p>
      <button className="quiet-button auth-workspace-link" type="button" onClick={() => router.push("/")}>返回示例工作台</button>
    </AuthFrame>
  );
}

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState<FormStatus>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setStatus(null);
    try {
      await apiRequest("/api/v1/auth/login", { email, password });
      router.push("/");
    } catch (error) {
      setStatus({ tone: "error", message: error instanceof Error ? error.message : "登录失败，请重试。" });
      setPending(false);
    }
  }

  return (
    <AuthFrame eyebrow="欢迎回来" title="继续校准你的职业表达。" description="登录后可继续查看已确认事实与待审核建议。">
      <form className="auth-form" onSubmit={submit}>
        <div className="form-field">
          <label htmlFor="login-email">邮箱</label>
          <input id="login-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </div>
        <PasswordField id="login-password" label="密码" autoComplete="current-password" value={password} onChange={setPassword} />
        <div className="form-links"><Link href="/reset-password">忘记密码？</Link></div>
        <StatusMessage status={status} />
        <button className="primary-button auth-submit" type="submit" disabled={pending}>{pending ? "正在登录…" : "登录"}</button>
      </form>
      <p className="auth-switch">还没有账号？<Link href="/register">使用邀请码注册</Link></p>
    </AuthFrame>
  );
}

export function VerifyEmailForm() {
  const [status, setStatus] = useState<FormStatus>({ tone: "success", message: "正在确认验证链接…" });
  const token = useHashToken();

  useEffect(() => {
    let active = true;
    async function verify() {
      await Promise.resolve();
      if (!active) return;
      if (!token) {
        setStatus({ tone: "error", message: "验证链接缺少令牌，请重新发送邮件。" });
        return;
      }
      try {
        await apiRequest("/api/v1/auth/email-verification/confirm", { token });
        if (active) setStatus({ tone: "success", message: "邮箱已验证。现在可以继续使用工作台。" });
      } catch (error) {
        if (active) setStatus({ tone: "error", message: error instanceof Error ? error.message : "验证失败，请重试。" });
      }
    }
    void verify();
    return () => { active = false; };
  }, [token]);

  return (
    <AuthFrame eyebrow="邮箱验证" title="确认这是你的邮箱。" description="验证成功后，通知和账号恢复邮件才能可靠送达。">
      <StatusMessage status={status} />
      <div className="auth-actions"><Link className="primary-button state-link" href="/login">前往登录</Link><Link className="quiet-button state-link" href="/register">重新注册或发送验证</Link></div>
    </AuthFrame>
  );
}

export function ResetPasswordForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState<FormStatus>(null);
  const token = useHashToken();
  const hasToken = Boolean(token);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setStatus(null);
    try {
      if (hasToken) {
        await apiRequest("/api/v1/auth/password-reset/confirm", { token, password });
        setStatus({ tone: "success", message: "密码已重设，请用新密码登录。" });
      } else {
        await apiRequest("/api/v1/auth/password-reset/request", { email });
        setStatus({ tone: "success", message: "若该邮箱已注册，重设链接已发送。请查收邮件。" });
      }
    } catch (error) {
      setStatus({ tone: "error", message: error instanceof Error ? error.message : "请求失败，请重试。" });
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthFrame eyebrow={hasToken ? "设置新密码" : "找回密码"} title={hasToken ? "设置一个新的登录密码。" : "把登录权限找回来。"} description={hasToken ? "成功后，所有旧登录会话将被安全撤销。" : "我们不会透露某个邮箱是否已注册。"}>
      <form className="auth-form" onSubmit={submit}>
        {hasToken ? <PasswordField id="reset-password" label="新密码" autoComplete="new-password" value={password} onChange={setPassword} /> : <div className="form-field"><label htmlFor="reset-email">邮箱</label><input id="reset-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></div>}
        <StatusMessage status={status} />
        <button className="primary-button auth-submit" type="submit" disabled={pending}>{pending ? "正在处理…" : hasToken ? "确认重设密码" : "发送重设链接"}</button>
      </form>
      <p className="auth-switch"><Link href="/login">返回登录</Link></p>
    </AuthFrame>
  );
}
