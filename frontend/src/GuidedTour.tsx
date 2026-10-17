import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { EditReceipt } from './EditReceipt';
import { date, n } from './api';
import type { PlayResult } from './Play';
import { getRecordedQuestion, previewWidgets, selectContext, selectWidgets, setTourView } from './tour/runtime';
import { revealTourWidget } from './tourWidgetReveal';
import type { ContextId, QuestionId, TourBundle, WidgetId } from './tour/types';
import { fillTourCopy as fill, TOUR_COPY as copy } from './tour/copy';
import { TourRichText } from './tourRichText';

type Rect={left:number;top:number;width:number;height:number;right:number;bottom:number};
type Clock={step:string;day:number;minute:number;speed:2|4|8;complete:boolean;result:PlayResult|null};
const button=(text:string)=>Array.from(document.querySelectorAll<HTMLButtonElement>('.app button')).find(item=>item.textContent?.trim()===text)||null;
function clippedRect(element:HTMLElement):Rect{
  const rect=element.getBoundingClientRect();let left=Math.max(12,rect.left),top=Math.max(12,rect.top),right=Math.min(innerWidth-12,rect.right),bottom=Math.min(innerHeight-12,rect.bottom);
  for(let parent=element.parentElement;parent;parent=parent.parentElement){const style=getComputedStyle(parent);if(/auto|scroll|hidden/.test(style.overflow+style.overflowY+style.overflowX)){const r=parent.getBoundingClientRect();left=Math.max(left,r.left);right=Math.min(right,r.right);top=Math.max(top,r.top);bottom=Math.min(bottom,r.bottom)}}
  return {left,top,right,bottom,width:Math.max(0,right-left),height:Math.max(0,bottom-top)};
}
export function GuidedTour({bundle,onExit,onReplay}:{bundle:TourBundle;onExit:()=>void;onReplay:()=>void}){
  const [step,setStep]=useState(1),[clock,setClock]=useState<Clock>({step:'report',day:-1,minute:0,speed:2,complete:false,result:null});
  const [question,setQuestion]=useState<QuestionId|'skip'|null>(null),[context,setContext]=useState<ContextId>('unchanged'),[selectedWidgets,setSelectedWidgets]=useState<WidgetId[]>([]),[widgetsAdded,setWidgetsAdded]=useState(false);
  const [answer,setAnswer]=useState(''),[typed,setTyped]=useState(''),[answered,setAnswered]=useState(false),[howOpened,setHowOpened]=useState(false);
  const [beat,setBeat]=useState(0),[progress,setProgress]=useState(0),[beatsDone,setBeatsDone]=useState(false);
  const [rect,setRect]=useState<Rect|null>(null),[position,setPosition]=useState({left:24,top:24,side:'bottom',arrow:24});
  const [chatMount,setChatMount]=useState<HTMLElement|null>(null),[contextMount,setContextMount]=useState<HTMLElement|null>(null),[figureMount,setFigureMount]=useState<HTMLElement|null>(null),[peakMount,setPeakMount]=useState<HTMLElement|null>(null);
  const coach=useRef<HTMLDivElement>(null),target=useRef<HTMLElement|null>(null),mainAction=useRef<(()=>void)|null>(null),finding=useRef<Rect|null>(null);
  const pendingWidget=useRef<WidgetId|null>(null),cancelReveal=useRef<(()=>void)|null>(null);
  useEffect(()=>()=>cancelReveal.current?.(),[]);
  const branch=bundle.branches[context],values=branch.recalculation;
  const card=()=>Array.from(document.querySelectorAll<HTMLElement>('.cohort-card')).find(item=>item.dataset.cohortId===bundle.meta.strawberry_card_id)||null;
  const advance=()=>setStep(value=>Math.min(15,value+1));
  function back(){if(step===14){setTourView('play');setStep(13)}else if(step>=2&&step<=6){setTourView('report');setStep(step-1)}}
  useEffect(()=>{const listener=(event:Event)=>{const state=(event as CustomEvent<Clock>).detail;setClock(state);setStep(current=>current===8&&state.step==='orders'?9:current===10&&state.step==='watch'?11:current===12&&state.step==='play'?13:current===13&&state.step==='results'?14:current)};window.addEventListener('scoop:tour-state',listener);return()=>window.removeEventListener('scoop:tour-state',listener)},[]);
  useEffect(()=>{document.body.classList.add('tour-active');return()=>{document.body.classList.remove('tour-active');delete document.body.dataset.tourStep}},[]);
  useLayoutEffect(()=>{document.body.dataset.tourStep=String(step)},[step]);
  useEffect(()=>{
    window.dispatchEvent(new CustomEvent('scoop:tour-open-chat',{detail:{open:step===5,findingId:bundle.base.detail.findings.find(f=>f.tag_id==='flavour:strawberry')?.id}}));
    if(step===3){setHowOpened(false);const how=card()?.querySelector<HTMLDetailsElement>('.cohort-how');if(how)how.open=false}
    if(step===4){const panel=document.querySelector<HTMLElement>('.cohort-panel');if(panel)panel.scrollTop=0}
    if(step===2)window.dispatchEvent(new Event('scoop:tour-report-locate'));
  },[step,bundle]);
  useEffect(()=>{const receive=(event:Event)=>{finding.current=(event as CustomEvent<Rect>).detail};window.addEventListener('scoop:tour-report-rect',receive);return()=>window.removeEventListener('scoop:tour-report-rect',receive)},[]);
  useEffect(()=>{if(!answer||step!==5)return;let frame=0,offset=0;setTyped('');setAnswered(false);const tick=()=>{offset=Math.min(answer.length,offset+40);setTyped(answer.slice(0,offset));if(offset<answer.length)frame=requestAnimationFrame(tick);else setAnswered(true)};frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame)},[answer,step]);
  useEffect(()=>{if(step!==7)return;setBeat(0);setProgress(0);setBeatsDone(false);const start=performance.now(),count=context==='unchanged'?1:4;let frame=0;const tick=(now:number)=>{const elapsed=now-start,index=Math.min(count-1,Math.floor(elapsed/1500));setBeat(index);setProgress(Math.min(1,(elapsed-index*1500)/1500));if(elapsed>=count*1500){setProgress(1);setBeatsDone(true)}else frame=requestAnimationFrame(tick)};frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame)},[step,context]);
  useLayoutEffect(()=>{
    let lastTarget:HTMLElement|null=null;
    const locate=()=>{
      const strawberry=card(),how=strawberry?.querySelector<HTMLDetailsElement>('.cohort-how'),area=strawberry?.querySelector<HTMLDetailsElement>('.cohort-context');
      if(step===3&&how?.open)setHowOpened(true);
      if((step===6||step===7)&&area)area.open=true;
      if(step===9){const groups=branch.snapshot.order_summary.groups.filter(group=>group.skus.some(sku=>bundle.meta.strawberry_skus.includes(sku)));document.querySelectorAll<HTMLDetailsElement>('.action-group').forEach(group=>{if(groups.some(item=>group.querySelector('summary h2')?.textContent===item.name))group.open=true});const row=Array.from(document.querySelectorAll<HTMLElement>('.action-product small')).find(item=>bundle.meta.strawberry_skus.some(sku=>item.textContent?.startsWith(sku)))?.closest('tr');const evidence=row?.nextElementSibling?.querySelector<HTMLDetailsElement>('.order-ledger');if(evidence&&!evidence.open){evidence.open=true;evidence.scrollIntoView({block:'nearest'})};}
      const node=step===1?document.querySelector<HTMLElement>('.report-column'):step===2?document.querySelector<HTMLElement>('.generated-report-frame'):step===3?(how?.open?how:how?.querySelector<HTMLElement>('summary')):step===4?document.querySelector<HTMLElement>('.cohort-panel'):step===5?document.querySelector<HTMLElement>('.discussion'):step===6?area:step===7?(context==='unchanged'?area:document.querySelector<HTMLElement>(['[data-tour-context]','[data-tour-factor]','[data-tour-cases]','[data-tour-peak]'][beat])):step===8?button('Review orders'):step===9?document.querySelector<HTMLElement>('.action-list'):step===10?button('Approve orders'):step===11?document.querySelector<HTMLElement>('.watch-step>.dashboard'):step===12?button('Next: Play'):step===13?(clock.complete?button('See results'):document.querySelector<HTMLElement>('.play')):step===14?document.querySelector<HTMLElement>('.play-outcomes'):null;
      target.current=node||null;
      if(node&&node!==lastTarget){if(step===2)window.dispatchEvent(new Event('scoop:tour-report-locate'));else node.scrollIntoView({block:'nearest',inline:'nearest'});lastTarget=node}
      const next=step===2?finding.current:node?clippedRect(node):null;setRect(previous=>JSON.stringify(previous)===JSON.stringify(next)?previous:next);
      setChatMount(document.querySelector<HTMLElement>('.discussion-scroll'));setContextMount(area||null);setFigureMount(strawberry?.querySelector<HTMLElement>('.cohort-numbers')||null);setPeakMount(document.querySelector<HTMLElement>('.cohort-preview-row'));
      document.querySelectorAll<HTMLInputElement>('.app input[type="range"],.app .action-list input').forEach(input=>{input.disabled=true});
      document.querySelectorAll<HTMLElement>('.dashboard-widget[draggable]').forEach(item=>item.draggable=false);
      if(step===11&&pendingWidget.current){const title=branch.widgets[pendingWidget.current].spec.title,widget=Array.from(document.querySelectorAll('.dashboard-widget h3')).find(item=>item.textContent===title)?.closest('article'),panel=document.querySelector<HTMLElement>('.watch-step>.dashboard');if(widget&&panel){cancelReveal.current?.();cancelReveal.current=revealTourWidget(widget,panel);pendingWidget.current=null}}
      if(step===11&&widgetsAdded&&selectedWidgets.length){const cards=Array.from(document.querySelectorAll('.dashboard-widget h3')),added=selectedWidgets.map(id=>cards.find(item=>item.textContent===branch.widgets[id].spec.title));if(added.every(Boolean))setStep(12)}
    };
    locate();const timer=setInterval(locate,100);return()=>clearInterval(timer);
  },[step,selectedWidgets,widgetsAdded,clock.complete,context,beat,branch,bundle]);
  useEffect(()=>{if(chatMount&&typed)chatMount.scrollTop=chatMount.scrollHeight},[chatMount,typed]);
  useLayoutEffect(()=>{
    if(!rect||!coach.current)return;const width=coach.current.offsetWidth,height=coach.current.offsetHeight,gap=20;
    const alignedTop=Math.max(16,Math.min(innerHeight-height-16,rect.top)),alignedLeft=Math.max(16,Math.min(innerWidth-width-16,rect.left));
    const candidates=[{left:rect.left-width-gap,top:alignedTop,side:'right'},{left:rect.right+gap,top:alignedTop,side:'left'},{left:alignedLeft,top:rect.top-height-gap,side:'bottom'},{left:alignedLeft,top:rect.bottom+gap,side:'top'}];
    const fits=(p:{left:number;top:number})=>p.left>=16&&p.left+width<=innerWidth-16&&p.top>=16&&p.top+height<=innerHeight-16;
    const chosen=candidates.find(fits)||{left:innerWidth-width-16,top:16,side:'left'};
    const arrow=chosen.side==='left'||chosen.side==='right'?Math.max(20,Math.min(height-20,rect.top+rect.height/2-chosen.top)):Math.max(20,Math.min(width-20,rect.left+rect.width/2-chosen.left));setPosition({...chosen,arrow});
  },[rect,step,typed,answered,beatsDone,clock.day,clock.minute]);
  useEffect(()=>{
    const nativeInteraction=[1,2,3,9].includes(step)||[8,10,12].includes(step)||(step===13);
    const allowed=(node:EventTarget|null)=>node instanceof Node&&(coach.current?.contains(node)||(nativeInteraction&&target.current?.contains(node)&&(step!==9||(node instanceof Element&&!!node.closest('.action-group')))));
    const guard=(event:Event)=>{if(event.type==='wheel'&&event.target instanceof Node&&(target.current?.contains(event.target)||document.querySelector('.cohort-panel')?.contains(event.target)))return;if(!allowed(event.target)){event.preventDefault();event.stopImmediatePropagation();if(event.type==='focusin')coach.current?.querySelector<HTMLButtonElement>('button')?.focus()}};
    const key=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();onExit();return}if(event.key==='ArrowLeft'&&([2,3,4,5,6,14].includes(step))){event.preventDefault();event.stopImmediatePropagation();back();return}if((event.key==='Enter'||event.key===' ')&&mainAction.current&&!(event.target instanceof Element&&event.target.closest('button,summary'))){event.preventDefault();event.stopImmediatePropagation();mainAction.current();return}if(event.key==='Tab'){const nodes=[...(coach.current?.querySelectorAll<HTMLElement>('button:not(:disabled)')||[]),...(nativeInteraction?(target.current?.matches('button,summary')?[target.current]:target.current?.querySelectorAll<HTMLElement>('button:not(:disabled),summary')||[]):[])].filter(node=>node.offsetParent!==null);if(nodes.length){event.preventDefault();const index=nodes.indexOf(document.activeElement as HTMLElement);nodes[(index+(event.shiftKey?-1:1)+nodes.length)%nodes.length].focus()}return}if(!allowed(event.target)){event.preventDefault();event.stopImmediatePropagation()}};
    document.addEventListener('pointerdown',guard,true);document.addEventListener('click',guard,true);document.addEventListener('wheel',guard,{capture:true,passive:false});document.addEventListener('keydown',key,true);document.addEventListener('focusin',guard,true);
    return()=>{document.removeEventListener('pointerdown',guard,true);document.removeEventListener('click',guard,true);document.removeEventListener('wheel',guard,true);document.removeEventListener('keydown',key,true);document.removeEventListener('focusin',guard,true)};
  },[step,onExit,rect,clock.complete]);
  const data=step<=14?copy.steps[step as keyof typeof copy.steps]:null;
  let body:string=data?.body||'';
  if(step===2)body=fill(body,{effect:n(bundle.meta.effect,0)});
  if(step===7)body=fill(context==='unchanged'?copy.recalculation.unchanged:context==='growing'&&values.n>0?copy.recalculation.growingWithCut:copy.recalculation[context],{f_before:values.f_before.toFixed(2),f_after:values.f_after.toFixed(2),before:n(values.before),after:n(values.after),p_before:values.p_before.toFixed(1),p_after:values.p_after.toFixed(1),n:n(values.n)});
  let eventLine='';
  if(step===13&&clock.result){const today=clock.result.dates[Math.max(0,clock.day)],moments=branch.moments,events=[{day:moments.heat_date,minute:0,text:fill(copy.events.heat,{date:date(moments.heat_date),temp:bundle.meta.heat_temp.toFixed(1)})}];if(moments.strawberry_arrival){const e=moments.strawberry_arrival;events.push({day:e.date,minute:e.minute,text:fill(copy.events.arrival,{date:date(e.date),time:e.time,units:n(e.units)})})}if(moments.stockout){const e=moments.stockout;events.push({day:e.date,minute:e.minute,text:fill(copy.events.stockout,{date:date(e.date),time:e.time,product:e.product})})}events.sort((a,b)=>a.day.localeCompare(b.day)||a.minute-b.minute);for(const e of events)if(e.day<today||(e.day===today&&clock.minute>=e.minute))eventLine=e.text;if(clock.complete){body=copy.events.endBody;eventLine=''}}
  const canNext=[1,2,4,9,14].includes(step)||(step===3&&howOpened)||(step===5&&answered)||(step===7&&beatsDone);
  mainAction.current=step===15?onExit:canNext?advance:null;
  const chooseQuestion=(id:QuestionId|'skip')=>{setQuestion(id);if(id==='skip'){setAnswer('');setTyped('');setAnswered(true)}else{setAnswered(false);setAnswer(getRecordedQuestion(id).reply)}};
  const chooseContext=(id:ContextId)=>{selectContext(id);setContext(id);setSelectedWidgets([]);setWidgetsAdded(false);setStep(7)};
  const chooseWidget=(id:WidgetId)=>{const removing=selectedWidgets.includes(id),ids=removing?selectedWidgets.filter(item=>item!==id):[...selectedWidgets,id];cancelReveal.current?.();pendingWidget.current=removing?null:id;setSelectedWidgets(ids);previewWidgets(ids)};
  const interpolated=(before:number,after:number,index:number)=>beat<index?before:beat>index?after:before+(after-before)*progress;
  const answerPortal=chatMount&&typed&&step===5?createPortal(<div className="chat-message assistant tour-recorded" aria-live="polite"><span>{copy.recorded}</span><p>{typed}</p></div>,chatMount):null;
  const contextPortal=contextMount&&(step===6||step===7)&&context!=='unchanged'?createPortal(<div className="tour-context-result"><div data-tour-context>{copy.contexts[context]}</div>{step===7&&branch.edit&&<EditReceipt edit={branch.edit} detail={branch.snapshot.detail} path={`/plans/${bundle.plan_id}`} onChanged={()=>{}} disabled/>}</div>,contextMount):null;
  const figures=step===7&&context!=='unchanged'&&figureMount?createPortal(<div className="tour-recalculation"><strong data-tour-factor>{interpolated(values.f_before,values.f_after,1).toFixed(2)}×</strong><strong data-tour-cases>{n(Math.round(interpolated(values.before,values.after,2)))} cases</strong></div>,figureMount):null;
  const peak=step===7&&context!=='unchanged'&&peakMount?createPortal(<strong className="tour-recalculation-peak" data-tour-peak>{interpolated(values.p_before,values.p_after,3).toFixed(1)} pallets</strong>,peakMount):null;
  if(step===15)return <div className="tour-modal-shade"><section ref={coach} className="tour-modal" role="dialog" aria-modal="true" aria-labelledby="tour-end-title"><h1 id="tour-end-title">{copy.end.title}</h1><p><TourRichText text={copy.end.body}/></p><div className="modal-actions"><button className="button primary" onClick={onExit}>{copy.end.explore}</button><button className="button ghost" onClick={onReplay}>{copy.end.replay}</button></div></section></div>;
  return <>{answerPortal}{contextPortal}{figures}{peak}<svg className="tour-spotlight" aria-hidden="true" width="100%" height="100%"><defs><mask id="tour-cutout"><rect width="100%" height="100%" fill="white"/>{rect&&<rect x={rect.left-6} y={rect.top-6} width={rect.width+12} height={rect.height+12} rx="12" fill="black"/>}</mask></defs><rect width="100%" height="100%" fill="rgba(15,35,28,.55)" mask="url(#tour-cutout)"/></svg>
    <div key={`${step}-${step===7?beat:0}`} ref={coach} className={`tour-coach arrow-${position.side}`} role="dialog" aria-modal="true" aria-labelledby="tour-instruction" data-tour-step={step} data-tour-beat={step===7?beat+1:undefined} style={{left:position.left,top:position.top,'--tour-arrow':`${position.arrow}px`} as React.CSSProperties}>
      <div className="tour-coach-top"><span>{`Step ${step} of 14`}</span><button className="text-button" onClick={onExit}>{copy.skip}</button></div><h2 id="tour-instruction">{data?.title}</h2><p><TourRichText text={body}/></p>{step===7&&<p className="tour-future-notice">{copy.futureNotice}</p>}{eventLine&&<p className="tour-event" aria-live="polite">{eventLine}</p>}
      {step===5&&<div className="tour-choices">{(Object.keys(copy.questions) as (QuestionId|'skip')[]).map(id=><button className="tour-choice" aria-pressed={question===id} disabled={!!question&&!answered} key={id} onClick={()=>chooseQuestion(id)}>{copy.questions[id]}</button>)}</div>}
      {step===6&&<div className="tour-choices">{(Object.keys(copy.contexts) as ContextId[]).map(id=><button className="tour-choice" key={id} onClick={()=>chooseContext(id)}>{copy.contexts[id]}</button>)}</div>}
      {step===11&&<><div className="tour-choices tour-widget-choices">{(Object.keys(copy.widgets) as WidgetId[]).map(id=><button className="tour-choice" aria-label={copy.widgets[id]} aria-pressed={selectedWidgets.includes(id)} disabled={widgetsAdded} key={id} onClick={()=>chooseWidget(id)}>{copy.widgets[id]}</button>)}</div><button className="button primary tour-next" disabled={!selectedWidgets.length||widgetsAdded} onClick={()=>{if(!selectedWidgets.length||widgetsAdded)return;selectWidgets(selectedWidgets);setWidgetsAdded(true)}}>{copy.addSelected}</button></>}
      {canNext&&<button className="button primary tour-next" onClick={advance}>{copy.next}</button>}
    </div></>;
}
