import { useEffect, useState } from 'react';
import App from './App';
import { GuidedTour } from './GuidedTour';
import { beginTour, endTour, loadTourBundle } from './tour/runtime';
import type { TourBundle } from './tour/types';
import { fillTourCopy, TOUR_COPY } from './tour/copy';
import './guidedTour.css';
import { TourRichText } from './tourRichText';

const visitedKey='scoop:tour-welcome-seen';
export default function TourHost(){
  const [mode,setMode]=useState<'explore'|'welcome'|'tour'>(()=>localStorage.getItem(visitedKey)?'explore':'welcome');
  const [bundle,setBundle]=useState<TourBundle|null>(null),[error,setError]=useState(''),[epoch,setEpoch]=useState(0);
  const [defaultReport,setDefaultReport]=useState(false);
  const [wide,setWide]=useState(()=>window.innerWidth>=1280);
  useEffect(()=>{const resize=()=>setWide(window.innerWidth>=1280);window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize)},[]);
  useEffect(()=>{if(mode!=='welcome')return;let active=true;setError('');loadTourBundle().then(value=>active&&setBundle(value)).catch(e=>active&&setError((e as Error).message));return()=>{active=false}},[mode]);
  useEffect(()=>()=>endTour(),[]);
  function explore(){endTour();localStorage.setItem(visitedKey,'1');setDefaultReport(value=>value||mode==='tour');setMode('explore');setEpoch(v=>v+1)}
  function start(){if(!bundle||!wide)return;beginTour(bundle);setDefaultReport(true);localStorage.setItem(visitedKey,'1');setEpoch(v=>v+1);setMode('tour')}
  return <>{mode!=='welcome'&&<App key={`${mode==='tour'?'tour':'explore'}-${epoch}`} initialReport={mode==='tour'||defaultReport} onTakeTour={()=>setMode('welcome')}/>}
    {mode==='welcome'&&<div className="tour-modal-shade"><section className="tour-modal" role="dialog" aria-modal="true" aria-labelledby="tour-welcome-title"><h1 id="tour-welcome-title">{TOUR_COPY.welcome.title}</h1>{bundle&&<p><TourRichText text={fillTourCopy(TOUR_COPY.welcome.body,{capacity:bundle.meta.capacity})}/></p>}{error&&<div className="error-banner" role="alert"><strong>Something needs attention</strong><p>{error}</p></div>}<div className="modal-actions">{wide&&<button className="button primary" disabled={!bundle||!!error} onClick={start}>{TOUR_COPY.welcome.start}</button>}<button className="button ghost" onClick={explore}>{TOUR_COPY.welcome.explore}</button></div></section></div>}
    {mode==='tour'&&bundle&&<GuidedTour key={epoch} bundle={bundle} onExit={explore} onReplay={start}/>}
  </>;
}
