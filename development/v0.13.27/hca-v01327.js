/* HCA v0.13.27 · schnelle Textilbilder in Dokumentvorschau und PDF */
(()=>{
'use strict';

const imageCache=new Map();
const imageUrl=value=>String(value?.image||value?.src||value?.url||value||'').trim();

async function imageBitmap(blob){
  if(typeof createImageBitmap==='function')return createImageBitmap(blob);
  return new Promise((resolve,reject)=>{
    const url=URL.createObjectURL(blob),img=new Image();
    img.onload=()=>{URL.revokeObjectURL(url);resolve(img)};
    img.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('Bild kann im Client nicht gelesen werden'))};
    img.src=url;
  });
}

async function convertImage(url){
  url=imageUrl(url);
  if(!/^https?:\/\//i.test(url))return '';
  if(imageCache.has(url))return imageCache.get(url);
  const task=(async()=>{
    const response=await productionFetch('/api/hca-shared/media/image-proxy?url='+encodeURIComponent(url),{cache:'force-cache',timeoutMs:7000});
    if(!response.ok)throw new Error('Bildproxy HTTP '+response.status);
    const bitmap=await imageBitmap(await response.blob());
    const width=Number(bitmap.width||bitmap.naturalWidth||0),height=Number(bitmap.height||bitmap.naturalHeight||0);
    if(!width||!height)throw new Error('Bild hat keine gültige Größe');
    const scale=Math.min(1,720/Math.max(width,height)),canvas=document.createElement('canvas');
    canvas.width=Math.max(1,Math.round(width*scale));canvas.height=Math.max(1,Math.round(height*scale));
    const context=canvas.getContext('2d');context.fillStyle='#fff';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(bitmap,0,0,canvas.width,canvas.height);
    if(typeof bitmap.close==='function')bitmap.close();
    return canvas.toDataURL('image/jpeg',0.82);
  })().catch(()=>"");
  imageCache.set(url,task);return task;
}

function references(config={}){
  const refs=[];
  const ref=(object,key)=>{const url=imageUrl(object?.[key]);return /^https?:\/\//i.test(url)?{object,key,url}:null};
  const list=list=>Array.isArray(list)?list.map((_,index)=>ref(list,index)).filter(Boolean):[];
  const add=value=>{if(value)refs.push(value)};
  const details=config.product_details&&typeof config.product_details==='object'?config.product_details:{};
  const selected=list(config.datasheet_images),products=list(config.product_images),gallery=list(details.gallery_images);
  const main=ref(details,'main_image')||selected[0]||products[0];add(main);
  const used=new Set(main?[main.url]:[]);
  for(const candidate of [...selected,...gallery,...products]){
    if(used.has(candidate.url))continue;
    used.add(candidate.url);add(candidate);
    if(used.size>=6)break; // Hauptbild plus höchstens fünf Galeriebilder wie im PDF.
  }
  for(const row of Array.isArray(details.color_images)?details.color_images:[]){
    if(!row||typeof row!=='object')continue;
    add(ref(row,'image')||ref(row,'src')||ref(row,'url'));
  }
  const wizard=config.wizard_config&&typeof config.wizard_config==='object'?config.wizard_config:{};
  const areas=Array.isArray(wizard.areas)?wizard.areas:(Array.isArray(details.refinement_areas)?details.refinement_areas:[]);
  for(const area of areas){
    if(!area||typeof area!=='object')continue;
    add(ref(area,'image')||ref(area,'src')||ref(area,'url')||list(area.images)[0]);
  }
  return refs;
}

async function parallel(rows,worker,limit=6){
  let cursor=0;const output=new Array(rows.length);
  await Promise.all(Array.from({length:Math.min(limit,rows.length)},async()=>{while(cursor<rows.length){const index=cursor++;output[index]=await worker(rows[index],index)}}));
  return output;
}

async function preparePayload(payload,{embed=true}={}){
  const all=[];
  for(const item of payload.items||[]){if(!item?.config?.datasheet_enabled)continue;all.push(...references(item.config))}
  const unique=[...new Map(all.map(ref=>[ref.url,ref])).values()];
  const converted=await parallel(unique,async ref=>({url:ref.url,data:await convertImage(ref.url)}));
  const valid=converted.filter(row=>row.data);
  const byUrl=new Map(valid.map(row=>[row.url,row.data]));
  if(embed)for(const ref of all){const data=byUrl.get(ref.url);if(data)ref.object[ref.key]=data}
  if(valid.length)await productionFetch('/api/hca-shared/media/image-cache',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({images:valid}),timeoutMs:12000}).catch(()=>{});
  return payload;
}

async function currentPayload(embed=true){
  const payload=JSON.parse(JSON.stringify(businessQuotePayload()));
  payload.source_channel=activeBusinessQuote?.source_channel||'';payload.payment_term_id=activeBusinessQuote?.payment_term_id||'';
  return preparePayload(payload,{embed});
}

hcaV123DocumentPreview=async function(){
  if(!activeBusinessQuote)return;
  const button=document.querySelector('#businessQuoteDocumentPreview'),old=button?.textContent;
  if(button){button.disabled=true;button.textContent='Bilder werden vorbereitet …'}
  try{
    const payload=await currentPayload(true);
    const response=await productionFetch('/api/hca-shared/sales/quotes/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),cache:'no-store',timeoutMs:30000});
    if(!response.ok){let message='HTTP '+response.status;try{const data=await response.json();message=data.detail||data.error||message}catch{}throw new Error(message)}
    if(hcaV123PreviewUrl)URL.revokeObjectURL(hcaV123PreviewUrl);hcaV123PreviewUrl=URL.createObjectURL(await response.blob());
    const frame=document.querySelector('#businessDocumentPreviewFrame'),dialog=document.querySelector('#businessDocumentPreviewDialog');if(frame)frame.src=hcaV123PreviewUrl;if(dialog&&!dialog.open)dialog.showModal();
  }catch(error){alert('Dokumentenvorschau konnte nicht erstellt werden:\n'+(error.message||error))}
  finally{if(button){button.disabled=false;button.textContent=old||'◉ Dokumentenvorschau'}}
};

const previousSave=saveBusinessQuote;
saveBusinessQuote=async function(){try{await currentPayload(false)}catch{}return previousSave()};
const previousPrint=printBusinessQuote;
printBusinessQuote=async function(){try{await currentPayload(false)}catch{}return previousPrint()};
})();
