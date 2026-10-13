export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, { method, headers: body === undefined ? undefined : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === 'string' ? data.detail : data?.detail ? JSON.stringify(data.detail) : `Request failed (${response.status}). Please try again.`);
  }
  return response.json();
}
export const n = (value: number | undefined | null, digits = 0) => value == null || !Number.isFinite(value) ? '—' : value.toLocaleString('en-HK', { maximumFractionDigits: digits });
export const pct = (value: number | undefined | null) => value == null ? '—' : `${n(value * 100, 1)}%`;
export const date = (value: string) => value ? new Date(`${value.slice(0, 10)}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }) : '—';
export const fullDate = (value: string) => value ? new Date(`${value.slice(0, 10)}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }) : '—';
export const weekday = (value: string | number) => typeof value === 'number' ? ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][value] || String(value) : value;
export const plusDays = (value: string, days: number) => { const d = new Date(`${value.slice(0, 10)}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + days); return d.toISOString().slice(0, 10); };
export const monday = (value: string) => { const d = new Date(`${value.slice(0, 10)}T00:00:00Z`); d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7); return d.toISOString().slice(0, 10); };
