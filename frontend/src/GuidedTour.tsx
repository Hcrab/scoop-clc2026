import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { EditReceipt } from './EditReceipt';
import { date, n } from './api';
import type { PlayResult } from './Play';
import { getRecordedQuestion, selectContext, selectWidget, setTourView } from './tour/runtime';
import type { TourBundle } from './tour/types';
import { fillTourCopy as fill, TOUR_COPY as copy } from './tour/copy';

type ContextId=keyof typeof copy.contexts;
type Rect={left:number;top:number;width:number;height:number;right:number;bottom:number};
type Clock={step:string;day:number;minute:number;complete:boolean;result:PlayResult|null};
const button=(text:string)=>Array.from(document.querySelectorAll<HTMLButtonElement>('.app button')).find(item=>item.textContent?.trim()===text)||null;
function clippedRect(element:HTMLElement):Rect{
  const rect=element.getBoundingClientRect();let left=Math.max(12,rect.left),top=Math.max(12,rect.top),right=Math.min(innerWidth-12,rect.right),bottom=Math.min(innerHeight-12,rect.bottom);
  for(let parent=element.parentElement;parent;parent=parent.parentElement){const style=getComputedStyle(parent);if(/auto|scroll|hidden/.test(style.overflow+style.overflowY+style.overflowX)){const r=parent.getBoundingClientRect();left=Math.max(left,r.left);right=Math.min(right,r.right);top=Math.max(top,r.top);bottom=Math.min(bottom,r.bottom)}}
  return {left,top,right,bottom,width:Math.max(0,right-left),height:Math.max(0,bottom-top)};
}

export function GuidedTour({bundle,onExit,onReplay}:{bundle:TourBundle;onExit:()=>void;onReplay:()=>void}){
  const [step,setStep]=useState(1),[clock,setClock]=useState<Clock>({step:'report',day:-1,minute:0,complete:false,result:null});
  const [question,setQuestion]=useState<keyof typeof copy.questions|null>(null),[context,setContext]=useState<ContextId|null>(null),[widget,setWidget]=useState<keyof typeof copy.widgets|null>(null);
  const [answer,setAnswer]=useState(''),[typed,setTyped]=useState(''),[answered,setAnswered]=useState(false),[contextDone,setContextDone]=useState(false);
  const [branch,setBranch]=useState(bundle.branches.unchanged);
  const [rect,setRect]=useState<Rect|null>(null),[position,setPosition]=useState({left:24,top:24,side:'bottom',arrow:24});
  const [chatMount,setChatMount]=useState<HTMLElement|null>(null),[contextMount,setContextMount]=useState<HTMLElement|null>(null);
  const coach=useRef<HTMLDivElement>(null),target=useRef<HTMLElement|null>(null),mainAction=useRef<(()=>void)|null>(null),nextButton=useRef<HTMLButtonElement>(null);
  const card=()=>Array.from(document.querySelectorAll<HTMLElement>('.cohort-card')).find(item=>item.dataset.cohortId===bundle.meta.strawberry_card_id)||null;
  function advance(){setStep(value=>Math.min(10,value+1))}
  function back(){if(step===9){setTourView('play');setStep(8)}else if(step>=2&&step<=4){setTourView('report');setStep(step-1)}}
  useEffect(()=>{const listener=(event:Event)=>{const state=(event as CustomEvent<Clock>).detail;setClock(state);setStep(current=>current===5&&state.step==='orders'?6:current===6&&state.step==='watch'?7:current===7&&state.step==='play'?8:current===8&&state.step==='results'?9:current)};window.addEventListener('scoop:tour-state',listener);return()=>window.removeEventListener('scoop:tour-state',listener)},[]);
  useEffect(()=>{document.body.classList.add('tour-active');return()=>{document.body.classList.remove('tour-active');delete document.body.dataset.tourStep}},[]);
  useEffect(()=>{document.body.dataset.tourStep=String(step);window.dispatchEvent(new CustomEvent('scoop:tour-open-chat',{detail:{open:step===3||step===4,findingId:bundle.base.detail.findings.find(f=>f.tag_id==='flavour:strawberry')?.id}}));if(step===1){const how=card()?.querySelector<HTMLDetailsElement>('.cohort-how');if(how)how.open=false}if(step===3||step===4){setAnswer('');setTyped('');setAnswered(false);if(step===3)setQuestion(null)}},[step]);
  useEffect(()=>{if(!answer||(step!==3&&step!==4))return;let frame=0,offset=0;setTyped('');setAnswered(false);const tick=()=>{offset=Math.min(answer.length,offset+40);setTyped(answer.slice(0,offset));if(offset<answer.length)frame=requestAnimationFrame(tick);else{setAnswered(true);if(step===4&&context){setBranch(selectContext(context));setContextDone(true)}}};frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame)},[answer,context,step]);
  useEffect(()=>{
    let lastTarget:HTMLElement|null=null;
    const locate=()=>{
      const strawberry=card();
      if(step>=2&&step<=4){const how=strawberry?.querySelector<HTMLDetailsElement>('.cohort-how');if(how)how.open=true}
      if(step===4){const area=strawberry?.querySelector<HTMLDetailsElement>('.cohort-context');if(area)area.open=true}
      const node=step===1?strawberry?.querySelector<HTMLElement>('.cohort-how>summary'):step===2?strawberry?.querySelector<HTMLElement>('.drill-rows'):step===3?document.querySelector<HTMLElement>('.discussion'):step===4?strawberry?.querySelector<HTMLElement>('.cohort-context'):step===5?button('Review orders'):step===6?document.querySelector<HTMLElement>('.action-capacity'):step===7?(widget?button('Next: Play'):document.querySelector<HTMLElement>('.dashboard-grid')):step===8?(clock.complete?button('See results'):document.querySelector<HTMLElement>('.play-body')):step===9?document.querySelector<HTMLElement>('.play-outcomes'):null;
      target.current=node||null;
      if(node&&node!==lastTarget){if(step===7&&!widget)document.querySelector('.watch-step>.dashboard')?.scrollTo(0,0);else if(step!==8)node.scrollIntoView({block:'nearest',inline:'nearest'});lastTarget=node}
      const next=node?clippedRect(node):null;setRect(previous=>JSON.stringify(previous)===JSON.stringify(next)?previous:next);
      setChatMount(document.querySelector<HTMLElement>('.discussion-scroll'));setContextMount(strawberry?.querySelector<HTMLElement>('.cohort-context')||null);
      document.querySelectorAll<HTMLInputElement>('.app input[type="range"],.app .action-list input').forEach(input=>{input.disabled=true});
      document.querySelectorAll<HTMLElement>('.dashboard-widget[draggable]').forEach(item=>item.draggable=false);
    };
    locate();const timer=setInterval(locate,120);return()=>clearInterval(timer);
  },[step,widget,clock.complete,contextDone,bundle.meta.strawberry_card_id]);
  useEffect(()=>{if(chatMount&&typed)chatMount.scrollTop=chatMount.scrollHeight},[chatMount,typed]);
  useEffect(()=>{const how=card()?.querySelector<HTMLDetailsElement>('.cohort-how');if(step!==1||!how)return;const toggle=()=>{if(how.open)advance()};how.addEventListener('toggle',toggle);return()=>how.removeEventListener('toggle',toggle)},[step,rect]);
  useEffect(()=>{if(!coach.current)return;const observer=new ResizeObserver(()=>setRect(previous=>previous?{...previous}:previous));observer.observe(coach.current);return()=>observer.disconnect()},[step]);
  useLayoutEffect(()=>{
    if(!rect||!coach.current)return;const width=coach.current.offsetWidth,height=coach.current.offsetHeight,gap=20;
    const alignedTop=Math.max(16,Math.min(innerHeight-height-16,rect.top));
    const alignedLeft=Math.max(16,Math.min(innerWidth-width-16,rect.left));
    const candidates=[{left:rect.left-width-gap,top:alignedTop,side:'right'},{left:rect.right+gap,top:alignedTop,side:'left'},{left:alignedLeft,top:rect.top-height-gap,side:'bottom'},{left:alignedLeft,top:rect.bottom+gap,side:'top'}];
    const fits=(p:{left:number;top:number})=>p.left>=16&&p.left+width<=innerWidth-16&&p.top>=16&&p.top+height<=innerHeight-16;
    const chosen=candidates.find(fits)||{left:Math.min(innerWidth-width-16,Math.max(16,rect.left)),top:Math.max(16,rect.top-height-gap),side:'bottom'};
    chosen.left=Math.max(16,Math.min(innerWidth-width-16,chosen.left));chosen.top=Math.max(16,Math.min(innerHeight-height-16,chosen.top));
    const arrow=chosen.side==='left'||chosen.side==='right'?Math.max(20,Math.min(height-20,rect.top+rect.height/2-chosen.top)):Math.max(20,Math.min(width-20,rect.left+rect.width/2-chosen.left));setPosition({...chosen,arrow});
  },[rect,step,typed,contextDone,widget,answered]);
  useEffect(()=>{
    const nativeInteraction=step===1||step===2||step===5||step===6||(step===7&&!!widget)||(step===8&&clock.complete);
    const allowed=(node:EventTarget|null)=>node instanceof Node&&(coach.current?.contains(node)||(nativeInteraction&&target.current?.contains(node)));
    const guard=(event:Event)=>{if(event.type==='wheel'&&event.target instanceof Node&&target.current?.contains(event.target))return;if(!allowed(event.target)){event.preventDefault();event.stopImmediatePropagation();if(event.type==='focusin')coach.current?.querySelector<HTMLButtonElement>('button')?.focus()}};
    const key=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();onExit();return}if(event.key==='ArrowLeft'&&[2,3,4,9].includes(step)){event.preventDefault();event.stopImmediatePropagation();back();return}if((event.key==='Enter'||event.key===' ')&&mainAction.current){event.preventDefault();event.stopImmediatePropagation();mainAction.current();return}if(event.key==='Tab'){const nodes=[...(coach.current?.querySelectorAll<HTMLElement>('button:not(:disabled)')||[]),...(nativeInteraction?(target.current?.matches('button,summary')?[target.current]:target.current?.querySelectorAll<HTMLElement>('button:not(:disabled),summary')||[]):[])].filter(node=>node.offsetParent!==null);if(nodes.length){event.preventDefault();const index=nodes.indexOf(document.activeElement as HTMLElement);nodes[(index+(event.shiftKey?-1:1)+nodes.length)%nodes.length].focus()}return}if(!allowed(event.target)){event.preventDefault();event.stopImmediatePropagation()}};
    document.addEventListener('pointerdown',guard,true);document.addEventListener('click',guard,true);document.addEventListener('wheel',guard,{capture:true,passive:false});document.addEventListener('keydown',key,true);document.addEventListener('focusin',guard,true);
    return()=>{document.removeEventListener('pointerdown',guard,true);document.removeEventListener('click',guard,true);document.removeEventListener('wheel',guard,true);document.removeEventListener('keydown',key,true);document.removeEventListener('focusin',guard,true)};
  },[step,onExit,rect,widget,clock.complete]);
  const data=step<10?copy.steps[step as keyof typeof copy.steps]:null;
  let big:string=data?.big||'',small:string=data?.small||'';
  if(step===1)small=fill(small,{effect:n(bundle.meta.effect)});
  if(step===2)small=fill(small,{l1:n(bundle.meta.l1),l2:n(bundle.meta.l2),l3:n(bundle.meta.l3)});
  if(step===4&&contextDone)small=fill(context==='unchanged'?copy.contextUnchanged:copy.contextResult,{before:n(branch.before_cases),after:n(branch.after_cases)});
  if(step===6)small=fill(small,{cases:n(branch.total_cases),peak:n(branch.peak,1),capacity:n(branch.capacity)});
  if(step===7&&widget)big=copy.steps[7].afterBig;
  if(step===8&&clock.result){
    const result=clock.result,today=result.dates[Math.max(0,clock.day)],at=(day:string,minute=0)=>day<today||(day===today&&clock.minute>=minute);
    const moments=branch.moments;const events:{day:string;minute:number;text:string}[]=[{day:moments.heat_date,minute:0,text:fill(copy.steps[8].heat,{date:date(moments.heat_date)})}];
    if(moments.strawberry_arrival){const event=moments.strawberry_arrival;events.push({day:event.date,minute:event.minute,text:fill(copy.steps[8].arrival,{date:date(event.date),time:event.time,units:n(event.units)})})}
    if(moments.stockout){const event=moments.stockout;events.push({day:event.date,minute:event.minute,text:fill(copy.steps[8].stockout,{date:date(event.date),time:event.time,product:event.product})})}
    events.sort((a,b)=>a.day.localeCompare(b.day)||a.minute-b.minute);for(const event of events)if(at(event.day,event.minute))small=event.text;
    if(clock.complete){big=copy.steps[8].afterBig;small=fill(copy.steps[8].end,{end_date:date(result.end)})}
  }
  const canNext=step===2||step===9||(step===3&&answered)||(step===4&&contextDone);
  mainAction.current=step===10?onExit:canNext?advance:null;
  const chooseQuestion=(id:keyof typeof copy.questions)=>{setQuestion(id);setAnswer(getRecordedQuestion(id).reply)};
  const chooseContext=(id:ContextId)=>{if(id===context&&contextDone)return;setContext(id);setContextDone(false);const recorded=bundle.branches[id].answer;if(!recorded)throw new Error('Missing recorded context answer');setAnswer(recorded.reply)};
  const answerPortal=chatMount&&typed&&(step===3||step===4)?createPortal(<div className="chat-message assistant tour-recorded" aria-live="polite"><span>{copy.recorded}</span><p>{typed}</p></div>,chatMount):null;
  const receiptPortal=contextMount&&step===4&&contextDone&&branch.edit?createPortal(<div className="tour-context-result"><EditReceipt edit={branch.edit} detail={branch.snapshot.detail} path={`/plans/${bundle.plan_id}`} onChanged={()=>{}} disabled/></div>,contextMount):null;
  if(step===10)return <div className="tour-modal-shade"><section ref={coach} className="tour-modal" role="dialog" aria-modal="true" aria-labelledby="tour-end-title"><h1 id="tour-end-title">{copy.end.title}</h1><p>{copy.end.body}</p><div className="modal-actions"><button className="button primary" onClick={onExit}>{copy.end.explore}</button><button className="button ghost" onClick={onReplay}>{copy.end.replay}</button></div></section></div>;
  return <>{answerPortal}{receiptPortal}<svg className="tour-spotlight" aria-hidden="true" width="100%" height="100%"><defs><mask id="tour-cutout"><rect width="100%" height="100%" fill="white"/>{rect&&<rect x={rect.left-6} y={rect.top-6} width={rect.width+12} height={rect.height+12} rx="12" fill="black"/>}</mask></defs><rect width="100%" height="100%" fill="rgba(15,35,28,.55)" mask="url(#tour-cutout)"/></svg>
    <div key={step} ref={coach} className={`tour-coach arrow-${position.side}`} role="dialog" aria-modal="true" aria-labelledby="tour-instruction" data-tour-step={step} style={{left:position.left,top:position.top,'--tour-arrow':`${position.arrow}px`} as React.CSSProperties}>
      <div className="tour-coach-top"><span>{`Step ${step} of 10 · ${data?.screen}`}</span><button className="text-button" onClick={onExit}>{copy.skip}</button></div><h2 id="tour-instruction">{big}</h2><p>{small}</p>
      {step===3&&<div className="tour-choices">{(Object.keys(copy.questions) as (keyof typeof copy.questions)[]).map(id=><button className="tour-choice" aria-pressed={question===id} disabled={!!question&&!answered} key={id} onClick={()=>chooseQuestion(id)}>{copy.questions[id]}</button>)}</div>}
      {step===4&&<div className="tour-choices">{(Object.keys(copy.contexts) as ContextId[]).map(id=><button className="tour-choice" aria-pressed={context===id} disabled={!!context&&!contextDone} key={id} onClick={()=>chooseContext(id)}>{copy.contexts[id]}</button>)}</div>}
      {step===7&&!widget&&<div className="tour-choices">{(Object.keys(copy.widgets) as (keyof typeof copy.widgets)[]).map(id=><button className="tour-choice" key={id} onClick={()=>{selectWidget(id);setWidget(id)}}>{copy.widgets[id]}</button>)}</div>}
      {canNext&&<button ref={nextButton} className="button primary tour-next" onClick={advance}>{copy.next}</button>}
    </div></>;
}
