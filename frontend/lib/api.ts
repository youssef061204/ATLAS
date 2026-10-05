export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
export const API =
  process.env.NEXT_PUBLIC_API_URL ?? (DEMO_MODE ? "" : "http://localhost:8000");
export const GITHUB = "https://github.com/youssef061204/ATLAS";
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail),
    );
  }
  return response.json();
}
export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
