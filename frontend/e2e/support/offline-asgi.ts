import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import path from 'node:path';
import type { Page } from '@playwright/test';

export function offlineASGI() {
  const root=path.resolve('..');
  const process=spawn(path.join(root,'.venv','Scripts','python.exe'),
    [path.join(root,'backend','tests','support','offline_asgi.py')],
    {cwd:root,env:{...globalThis.process.env,PYTHONPATH:path.join(root,'backend'),
      PYTHONUTF8:'1',OMP_NUM_THREADS:'1',OPENBLAS_NUM_THREADS:'1'},stdio:['pipe','pipe','pipe']});
  let next=0,closed=false;
  const pending=new Map<number,{resolve:(value:any)=>void;reject:(error:Error)=>void}>();
  createInterface({input:process.stdout}).on('line',line=>{
    const result=JSON.parse(line), item=pending.get(result.id);
    if(!item)return;
    pending.delete(result.id);
    if(result.error)item.reject(new Error(result.error));
    else item.resolve(result);
  });
  // Python diagnostics are retained locally by the test runner, never sent upstream.
  process.stderr.on('data',chunk=>globalThis.process.stderr.write(chunk));
  process.on('exit',code=>{
    closed=true;
    for(const item of pending.values())item.reject(new Error(`ASGI transport exited (${code})`));
    pending.clear();
  });
  async function send(method:string,url:string,body?:string) {
    if(closed)throw new Error('ASGI transport is closed');
    const id=++next, target=new URL(url,'http://127.0.0.1:8009');
    const result=await new Promise<any>((resolve,reject)=>{
      pending.set(id,{resolve,reject});
      process.stdin.write(JSON.stringify({id,method,path:target.pathname+target.search,body})+'\n');
    });
    const content=Buffer.from(result.body,'base64');
    return {status:result.status,headers:result.headers,content,
      ok:()=>result.status>=200&&result.status<300,
      json:async()=>JSON.parse(content.toString('utf8')),text:async()=>content.toString('utf8')};
  }
  return {
    request:{get:(url:string)=>send('GET',url),
      post:(url:string,options?:{data?:unknown})=>send('POST',url,options?.data===undefined?undefined:JSON.stringify(options.data)),
      put:(url:string,options?:{data?:unknown})=>send('PUT',url,options?.data===undefined?undefined:JSON.stringify(options.data))},
    async attach(page:Page) {
      await page.route('http://127.0.0.1:8009/**',async route=>{
        const result=await send(route.request().method(),route.request().url(),route.request().postData()||undefined);
        await route.fulfill({status:result.status,headers:result.headers,body:result.content});
      });
    },
    close:()=>{
      closed=true;
      for(const item of pending.values())item.reject(new Error('ASGI transport closed during test teardown'));
      pending.clear();process.stdin.end();
    },
  };
}
