import { isTourActive, tourAssistant, tourRequest } from './tour/runtime';

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  if (isTourActive()) return tourRequest<T>(path, method, body);
  const response = await fetch(`/api${path}`, { method, headers: body === undefined ? undefined : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === 'string' ? data.detail : data?.detail ? JSON.stringify(data.detail) : `Request failed (${response.status}). Please try again.`);
  }
  return response.json();
}
export async function assistantStream<T>(path:string,body:unknown,onProgress:(event:{phase:string;label:string;tool?:string})=>void):Promise<T> {
  if (isTourActive()) return tourAssistant<T>(path, body, onProgress);
  const response=await fetch(`/api${path}/stream`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!response.ok){const error=await response.json().catch(()=>null);throw new Error(typeof error?.detail==='string'?error.detail:'The assistant could not start. Please try again.');}
  if(!response.body)throw new Error('The assistant connection is unavailable.');
  const reader=response.body.getReader(),decoder=new TextDecoder();let pending='';
  try{
    for(;;){
      const {value,done}=await reader.read();pending+=decoder.decode(value,{stream:!done});
      let boundary:number;
      while((boundary=pending.indexOf('\n\n'))>=0){
        const block=pending.slice(0,boundary);pending=pending.slice(boundary+2);
        const lines=block.split('\n'),event=lines.find(line=>line.startsWith('event:'))?.slice(6).trim();
        const data=lines.filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');
        if(!data)continue;
        const payload=JSON.parse(data);
        if(event==='progress')onProgress(payload);
        if(event==='error')throw new Error(payload.detail||'The assistant could not complete this request.');
        if(event==='result')return payload as T;
      }
      if(done)throw new Error('The connection ended before the response arrived. Refresh the plan to check whether your request was saved.');
    }
  }finally{reader.releaseLock();}
}
export const n = (value: number | undefined | null, digits = 0) => value == null || !Number.isFinite(value) ? '—' : value.toLocaleString('en-HK', { maximumFractionDigits: digits });
export const pct = (value: number | undefined | null) => value == null ? '—' : `${n(value * 100, 1)}%`;
export const date = (value: string) => value ? new Date(`${value.slice(0, 10)}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }) : '—';
export const fullDate = (value: string) => value ? new Date(`${value.slice(0, 10)}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }) : '—';
export const weekday = (value: string | number) => typeof value === 'number' ? ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][value] || String(value) : value;
export const plusDays = (value: string, days: number) => { const d = new Date(`${value.slice(0, 10)}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + days); return d.toISOString().slice(0, 10); };
export const monday = (value: string) => { const d = new Date(`${value.slice(0, 10)}T00:00:00Z`); d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7); return d.toISOString().slice(0, 10); };
