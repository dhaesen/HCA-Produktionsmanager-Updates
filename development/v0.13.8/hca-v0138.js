/* HCA v0.13.8 · dauerhafte Kundensuche und vollständige Artikeldatenblätter */
(()=>{
'use strict';

const H138={scheduled:false};
const uniq=a=>[...new Set((a||[]).map(x=>String(x||'').trim()).filter(Boolean))];
const esc=value=>typeof escapeHtml==='function'?escapeHtml(String(value??'')):String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function customerCache(){
  if(Array.isArray(window.businessCustomerCache))return window.businessCustomerCache;
  try{if(typeof businessCustomerCache!=='undefined'&&Array.isArray(businessCustomerCache))return businessCustomerCache}catch{}
  return [];
}
function customerRows(select){
  const cached=customerCache(),byId=new Map(cached.map(c=>[String(c.id),c]));
  return [...select.options].filter(o=>String(o.value||'').trim()).map(o=>{
    const c=byId.get(String(o.value))||{};
    const label=String(o.textContent||o.label||'').trim();
    return {id:String(o.value),label,sub:String(c.email||''),hay:[label,c.customer_no,c.company_name,c.first_name,c.last_name,c.email,c.phone].join(' ').toLocaleLowerCase('de-DE')};
  });
}
function upgradeCustomerSelect(select){
  if(!select||select.dataset.hca138Enhanced==='1'||select.closest('.hca138-customer-combo'))return;
  const old=select.closest('.hca137-customer-combo,.hca136-customer-combo');
  const parent=old?.parentNode||select.parentNode;if(!parent)return;
  const wrap=document.createElement('div');wrap.className='hca138-customer-combo';
  const input=document.createElement('input');input.type='text';input.className='text-input hca138-customer-input';input.autocomplete='off';input.placeholder='Kunde auswählen oder Anfangsbuchstaben eingeben …';input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.disabled=select.disabled;
  const toggle=document.createElement('button');toggle.type='button';toggle.className='hca138-combo-toggle';toggle.textContent='▾';toggle.title='Kundenliste öffnen';toggle.disabled=select.disabled;
  const list=document.createElement('div');list.className='hca138-customer-list hidden';list.setAttribute('role','listbox');
  const marker=old||select;parent.insertBefore(wrap,marker);wrap.append(input,toggle,list,select);if(old)old.remove();
  select.dataset.hca138Enhanced='1';select.classList.add('hca138-native-select');select.tabIndex=-1;
  let rows=customerRows(select),active=-1;
  const selected=()=>rows.find(r=>r.id===String(select.value));
  const sync=()=>{rows=customerRows(select);input.value=selected()?.label||'';input.disabled=select.disabled;toggle.disabled=select.disabled};
  const close=()=>{list.classList.add('hidden');input.setAttribute('aria-expanded','false');active=-1};
  const choose=row=>{select.value=row.id;input.value=row.label;close();select.dispatchEvent(new Event('change',{bubbles:true}));input.focus()};
  const render=(needle='')=>{
    rows=customerRows(select);
    const q=String(needle||'').trim().toLocaleLowerCase('de-DE');
    const found=rows.filter(r=>!q||r.hay.includes(q)).sort((a,b)=>{
      const ap=q&&a.hay.startsWith(q)?0:1,bp=q&&b.hay.startsWith(q)?0:1;return ap-bp||a.label.localeCompare(b.label,'de');
    }).slice(0,150);
    list.innerHTML=found.length?found.map(r=>'<button type="button" role="option" data-h138-id="'+esc(r.id)+'"><b>'+esc(r.label)+'</b>'+(r.sub?'<span>'+esc(r.sub)+'</span>':'')+'</button>').join(''):'<div class="hca138-no-result">Kein Kunde gefunden</div>';
    list.querySelectorAll('[data-h138-id]').forEach(button=>button.addEventListener('mousedown',event=>{event.preventDefault();const row=rows.find(r=>r.id===button.dataset.h138Id);if(row)choose(row)}));
    list.classList.remove('hidden');input.setAttribute('aria-expanded','true');active=-1;
  };
  input.addEventListener('focus',()=>render(input.value===(selected()?.label||'')?'':input.value));
  input.addEventListener('input',()=>render(input.value));
  toggle.addEventListener('click',()=>list.classList.contains('hidden')?render(''):close());
  input.addEventListener('keydown',event=>{
    const buttons=[...list.querySelectorAll('[data-h138-id]')];
    if(event.key==='ArrowDown'){event.preventDefault();if(list.classList.contains('hidden'))render(input.value);active=Math.min(active+1,buttons.length-1);buttons[active]?.focus()}
    else if(event.key==='Enter'){const exact=rows.find(r=>r.label.toLocaleLowerCase('de-DE')===input.value.trim().toLocaleLowerCase('de-DE'));if(exact){event.preventDefault();choose(exact)}}
    else if(event.key==='Escape'){close();sync()}
  });
  list.addEventListener('keydown',event=>{
    const buttons=[...list.querySelectorAll('[data-h138-id]')],index=buttons.indexOf(document.activeElement);
    if(event.key==='ArrowDown'){event.preventDefault();buttons[Math.min(index+1,buttons.length-1)]?.focus()}
    else if(event.key==='ArrowUp'){event.preventDefault();if(index<=0)input.focus();else buttons[index-1]?.focus()}
    else if(event.key==='Enter'){event.preventDefault();document.activeElement?.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))}
    else if(event.key==='Escape'){close();input.focus()}
  });
  wrap.addEventListener('focusout',()=>setTimeout(()=>{if(!wrap.contains(document.activeElement)){close();sync()}},80));
  select.addEventListener('change',sync);sync();
}
function scanCustomerSelect(){H138.scheduled=false;upgradeCustomerSelect(document.querySelector('#bqCustomer'))}
function scheduleScan(){if(H138.scheduled)return;H138.scheduled=true;queueMicrotask(scanCustomerSelect)}
new MutationObserver(scheduleScan).observe(document.documentElement,{childList:true,subtree:true});
document.addEventListener('focusin',event=>{if(event.target?.id==='bqCustomer')scheduleScan()},true);
scheduleScan();window.addEventListener('DOMContentLoaded',scheduleScan,{once:true});

function imageUrl(row){return String(row?.image||row?.src||row?.url||'').trim()}
function colorImages(main={}){
  const direct=Array.isArray(main.color_images)?main.color_images:[];
  const variants=Array.isArray(main._variants)?main._variants:[];
  const rows=[...direct,...variants.map(v=>({name:v.color||v.name||'',image:v.color_image||v.image||'',erp_code:v.erp_code||v.code_erp||''}))];
  const seen=new Set();return rows.filter(row=>{const key=[row?.name,imageUrl(row)].join('|');if(!row?.name&&!imageUrl(row)||seen.has(key))return false;seen.add(key);return true});
}
function refinementAreas(main={},config={}){
  const wizard=Array.isArray(config?.wizard_config?.areas)?config.wizard_config.areas:[];
  return wizard.length?wizard:(Array.isArray(main.refinement_areas)?main.refinement_areas:[]);
}
function safeProductDetails(main={}){
  const images=uniq([...(Array.isArray(main.images)?main.images:[]),main.image]);
  return {name:main.name||'',sku:main.parent_sku||main.base_sku||main.sku||'',description:main.description||'',short_description:main.short_description||'',manufacturer:main.manufacturer||main.brand||'',weight:main.weight||'',dimensions:main.dimensions||{},attributes:Array.isArray(main.attributes)?main.attributes:[],categories:Array.isArray(main.categories)?main.categories:[],permalink:main.permalink||'',main_image:main.main_image||images[0]||'',gallery_images:Array.isArray(main.gallery_images)?main.gallery_images:images.slice(1),color_images:colorImages(main),refinement_areas:refinementAreas(main,{})};
}
const previousSelectProduct=window.hcaSelectMainProduct;
if(previousSelectProduct)window.hcaSelectMainProduct=function(line,main){previousSelectProduct(line,main);line.config=line.config||{};line.config.product_details=safeProductDetails(main)};

function methodName(assignment={}){
  const method=assignment.method&&typeof assignment.method==='object'?assignment.method:{};
  return String(method.name||method.label||assignment.druckart_name||method.code||assignment.druckart_code||assignment.druckart_id||'Veredelungsart').trim();
}
function visualSummary(line,i){
  const cfg=line.config||{},details=cfg.product_details||{},colors=Array.isArray(details.color_images)?details.color_images:[],areas=refinementAreas({},cfg).length?refinementAreas({},cfg):(details.refinement_areas||[]);
  if(!cfg.datasheet_enabled||(!colors.length&&!areas.length))return '';
  const colorHtml=colors.length?'<section><b>Farbvarianten</b><small>Alle Varianten werden in das Datenblatt übernommen.</small><div class="hca138-thumb-grid">'+colors.map(row=>'<div>'+(imageUrl(row)?'<img src="'+esc(imageUrl(row))+'" alt="'+esc(row.name||'Farbe')+'" loading="lazy">':'<span class="empty">Kein Bild</span>')+'<label>'+esc(row.name||'Farbvariante')+'</label></div>').join('')+'</div></section>':'';
  const areaHtml=areas.length?'<section><b>Mögliche Veredelungen</b><small>Positionen, Verfahren und Positionsbilder werden vollständig übernommen.</small><div class="hca138-area-list">'+areas.map(area=>{const assignments=Array.isArray(area.assignments)?area.assignments:[],names=uniq(assignments.map(methodName));const src=imageUrl(area)||imageUrl((area.images||[])[0]);return '<div>'+(src?'<img src="'+esc(src)+'" alt="'+esc(area.name||'Veredelungsposition')+'" loading="lazy">':'')+'<span><strong>'+esc(area.name||area.position||'Veredelungsposition')+'</strong><small>'+esc(names.join(', ')||'Verfahren gemäß Produktkonfiguration')+'</small></span></div>'}).join('')+'</div></section>':'';
  return '<div class="hca138-datasheet-details" data-h138-line="'+i+'">'+colorHtml+areaHtml+'</div>';
}
const previousLineHtml=window.businessQuoteLineHtml;
if(previousLineHtml)window.businessQuoteLineHtml=function(line,i,locked=false){const html=previousLineHtml(line,i,locked),extra=visualSummary(line,i);if(!extra)return html;const at=html.lastIndexOf('</article>');return at>=0?html.slice(0,at)+extra+html.slice(at):html+extra};
})();
