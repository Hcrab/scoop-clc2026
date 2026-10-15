import { useState } from 'react';
import type { Product } from './types';
import { productVisuals, type ProductVisual } from './productVisuals';
import './productIcon.css';

type Props = {sku:string|null|undefined;product?:Partial<Product>;size?:32|48|96;decorative?:boolean;absoluteUrl?:boolean};

const palette:Record<string,string> = {
  almond:'#c79d69',apple:'#b9cc79',berry:'#a75b83',black_sesame:'#67616c',butter:'#edc971',caramel:'#bf8551',
  chocolate:'#755044',citrus:'#f4c955',coconut:'#f2e6d2',coffee:'#9b7056',cookies:'#ae9077',dark_chocolate:'#563c3d',
  dragon_fruit:'#e677a0',durian:'#d3cb75',guava:'#f3a39c',hazelnut:'#ad825f',hojicha:'#a47a51',lemon:'#f1db71',
  lychee:'#f4cbd3',macadamia:'#d9c39b',mango:'#f4b954',matcha:'#85a67c',milk:'#efe6d2',milk_tea:'#b59a7c',
  mint:'#95cdb8',mixed_fruit:'#e7a78a',passion_fruit:'#efc05b',peach:'#f5b49a',peanut:'#c69b6d',pineapple:'#eacb62',
  pistachio:'#aabd82',raspberry:'#c9677d',red_bean:'#ad6c70',strawberry:'#e98088',taro:'#bd9cc6',tea:'#9eb48b',
  toffee:'#c39566',vanilla:'#f0ddab',watermelon:'#e8828c',white_chocolate:'#eee3cd',yogurt:'#f5e8d6',
};

function visualFor(sku:string|null|undefined, product?:Partial<Product>):ProductVisual {
  if (sku && Object.hasOwn(productVisuals,sku)) return productVisuals[sku];
  const tags=product?.tags||[];
  return {
    name:product?.name||sku||'Product',
    format:product?.format||'cup',
    flavours:tags.filter(tag=>tag.dimension==='flavour').map(tag=>tag.id.replace(/^flavour:/,'')),
    features:tags.filter(tag=>tag.dimension==='feature').map(tag=>tag.id.replace(/^feature:/,'')),
  };
}

function Silhouette({visual}:{visual:ProductVisual}) {
  const base=palette[visual.flavours[0]]||'#c8d4b7';
  const second=palette[visual.flavours[1]]||base;
  const twoTone=visual.flavours.length>1;
  const coated=visual.features.includes('choc_coated');
  const filled=visual.features.includes('filled');
  const fruit=visual.features.includes('fruit_pieces');
  const crunchy=visual.features.includes('crunchy');
  const flavour=<><path d="M31 23h34v44H31z" fill={base}/>{twoTone&&<path d="M48 23h17v44H48z" fill={second}/>}</>;
  let shape;
  switch(visual.format){
    case 'stick': shape=<><rect x="44" y="65" width="8" height="20" rx="4" fill="#c39263"/><rect x="27" y="12" width="42" height="61" rx="20" fill={base}/>{twoTone&&<path d="M48 12c12 0 21 9 21 21v20c0 11-9 20-21 20z" fill={second}/>}<path d="M28 47c6 5 12 5 18 0s14-5 22 0" fill="none" stroke="#fff" strokeOpacity=".42" strokeWidth="3"/></>;
      break;
    case 'cup': shape=<><path d="M20 35h56l-8 43c-1 5-5 8-10 8H38c-5 0-9-3-10-8z" fill={base}/>{twoTone&&<path d="M48 35h28l-8 43c-1 5-5 8-10 8H48z" fill={second}/>}<ellipse cx="48" cy="35" rx="30" ry="8" fill="#f6f1df"/><ellipse cx="48" cy="34" rx="25" ry="5" fill={base}/><path d="M23 53h50" stroke="#fff" strokeOpacity=".5" strokeWidth="3"/></>;
      break;
    case 'tub': shape=<><path d="M18 29h60l-6 50c-.5 5-5 8-10 8H34c-5 0-9.5-3-10-8z" fill={base}/>{twoTone&&<path d="M48 29h30l-6 50c-.5 5-5 8-10 8H48z" fill={second}/>}<rect x="14" y="22" width="68" height="12" rx="5" fill="#f5ead7"/><rect x="19" y="48" width="58" height="22" rx="6" fill="#fff" fillOpacity=".35"/></>;
      break;
    case 'cone': shape=<><path d="M27 48h42L49 88h-2z" fill="#ce9b65"/><path d="M32 57l31 20M64 57L33 77" stroke="#af7b50" strokeWidth="2"/><circle cx="48" cy="41" r="24" fill={base}/>{twoTone&&<path d="M48 17a24 24 0 0 1 0 48z" fill={second}/>}<path d="M26 49c6-3 11-3 16 0s11 3 16 0 8-3 13 0" fill="none" stroke="#f5e9d9" strokeWidth="4"/></>;
      break;
    case 'sandwich': shape=<><rect x="17" y="29" width="62" height="45" rx="8" fill="#bd916b"/><rect x="18" y="36" width="60" height="29" rx="5" fill={base}/>{twoTone&&<path d="M48 36h30v29H48z" fill={second}/>}<rect x="17" y="25" width="62" height="10" rx="5" fill="#d6aa7c"/><rect x="17" y="66" width="62" height="10" rx="5" fill="#d6aa7c"/></>;
      break;
    case 'multipack': shape=<><rect x="16" y="23" width="64" height="59" rx="7" fill="#f5ead6" stroke="#b7a98c" strokeWidth="2"/><path d="M16 34h64" stroke="#b7a98c" strokeWidth="2"/><rect x="25" y="42" width="12" height="26" rx="6" fill={base}/><rect x="42" y="42" width="12" height="26" rx="6" fill={second}/><rect x="59" y="42" width="12" height="26" rx="6" fill={base}/><path d="M30 67v7m18-7v7m18-7v7" stroke="#b7895d" strokeWidth="4" strokeLinecap="round"/></>;
      break;
    case 'mochi': shape=<><ellipse cx="48" cy="74" rx="35" ry="9" fill="#d2c5b8"/><path d="M13 63c0-15 12-27 27-27s26 12 26 27c0 8-8 14-26 14S13 71 13 63z" fill={base}/><path d="M44 64c0-14 9-26 21-26s19 11 19 25c0 8-8 14-20 14S44 72 44 64z" fill={second}/><path d="M46 65c5 3 11 4 18 0" fill="none" stroke="#fff" strokeOpacity=".5" strokeWidth="3"/></>;
      break;
    default: shape=<><circle cx="48" cy="48" r="30" fill={base}/>{flavour}</>;
  }
  return <svg className="product-icon-fallback" viewBox="0 0 96 96" aria-hidden="true" focusable="false"><circle cx="48" cy="48" r="47" fill="#f7f4e9"/>{shape}{coated&&<path d="M24 31c9-8 14 1 22-6s15-3 26 2" fill="none" stroke="#61463c" strokeWidth="8" strokeLinecap="round"/>}{fruit&&<><circle cx="38" cy="40" r="3" fill="#c94d62"/><circle cx="57" cy="54" r="3" fill="#c94d62"/><circle cx="48" cy="31" r="2" fill="#c94d62"/></>}{filled&&<circle cx="48" cy="52" r="7" fill="#f8e8c0" stroke="#ad7a5b" strokeWidth="2"/>}{crunchy&&<><path d="M32 52l4-3 3 4m16-15 4-3 3 4M53 65l4-3 3 4" fill="none" stroke="#805a45" strokeWidth="2" strokeLinecap="round"/></>}</svg>;
}

export function ProductIcon({sku,product,size=48,decorative=false,absoluteUrl=false}:Props) {
  const visual=visualFor(sku,product);
  const known=!!sku&&Object.hasOwn(productVisuals,sku);
  const [failedSku,setFailedSku]=useState<string|null>(null);
  const url=known?`/products/${sku}.webp`:null;
  return <span className="product-icon" style={{width:size,height:size}} role={decorative?undefined:'img'} aria-label={decorative?undefined:visual.name} aria-hidden={decorative?'true':undefined}>
    <Silhouette visual={visual}/>{url&&failedSku!==sku&&<img src={absoluteUrl?new URL(url,window.location.origin).href:url} alt="" onError={()=>setFailedSku(sku||null)}/>}
  </span>;
}
