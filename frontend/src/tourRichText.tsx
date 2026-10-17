export function TourRichText({text}:{text:string}){
  return <>{text.split(/(\*\*[^*]+\*\*)/g).map((part,index)=>part.startsWith('**')&&part.endsWith('**')?<strong key={index}>{part.slice(2,-2)}</strong>:part)}</>;
}
