const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

function csrfToken() {
  return document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith("rjm_csrf="))
    ?.split("=")[1];
}

export async function apiRequest(path: string, init: RequestInit = {}, csrf = false) {
  const response = await fetch(`${apiBase}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(csrf && csrfToken() ? { "X-CSRF-Token": decodeURIComponent(csrfToken() ?? "") } : {}),
      ...init.headers
    }
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "请求暂时无法完成，请稍后重试。");
  }
  return response;
}
