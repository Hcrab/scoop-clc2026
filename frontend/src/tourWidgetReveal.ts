/** Bring a newly chosen native widget into the Watch panel, then give it a small pop. */
export function revealTourWidget(widget:HTMLElement, panel:HTMLElement):()=>void {
  const card=widget.getBoundingClientRect(),viewport=panel.getBoundingClientRect();
  const from=panel.scrollTop;
  const to=Math.max(0,Math.min(panel.scrollHeight-panel.clientHeight,
    from+card.top-viewport.top-(panel.clientHeight-Math.min(card.height,panel.clientHeight))/2));
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){panel.scrollTop=to;return()=>{}}
  let frame=0,animation:Animation|undefined;
  const started=performance.now();
  const scroll=(now:number)=>{
    if(!widget.isConnected||!panel.isConnected)return;
    const progress=Math.min(1,(now-started)/280);
    panel.scrollTop=from+(to-from)*(1-(1-progress)**3);
    if(progress<1)frame=requestAnimationFrame(scroll);
    else animation=widget.animate([
      {transform:'scale(.96)',opacity:.7,boxShadow:'0 0 0 0 rgba(32,90,78,0)'},
      {transform:'scale(1.025)',opacity:1,boxShadow:'0 0 0 4px rgba(32,90,78,.16)',offset:.65},
      {transform:'scale(1)',opacity:1,boxShadow:'0 0 0 0 rgba(32,90,78,0)'},
    ],{duration:420,easing:'cubic-bezier(.2,.75,.25,1)'});
  };
  frame=requestAnimationFrame(scroll);
  return()=>{cancelAnimationFrame(frame);animation?.cancel()};
}
