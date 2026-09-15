/* HCA v0.13.7 · echte Kundensuche, Artikelbilder und Angebotsdatenblätter */
(()=>{
'use strict';
const H137={customerOpen:false,invoiceTimers:{}};
const uniq=a=>[...new Set((a||[]).map(x=>String(x||'').trim()).filter(Boolean))];
function productImages(x={}){
  return uniq([...(Array.isArray(x.images)?x.images:[]),x.image,...(Array.isArray(x._variants)?x._variants.flatMap(v=>Array.isArray(v.images)?v.images:[v.image]):[])]).slice(0,10);
}
function productDetails(x={}){
  return {
    name:x.name||'',sku:x.parent_sku||x.base_sku||x.sku||'',
    description:x.description||'',short_description:x.short_description||'',
    manufacturer:x.manufacturer||'',supplier:x.supplier||'',weight:x.weight||'',
    dimensions:x.dimensions||{},attributes:Array.isArray(x.attributes)?x.attributes:[],
    categories:Array.isArray(x.categories)?x.categories:[],permalink:x.permalink||''
  };
}
function applyProductMeta(line,main){
  if(!line||!main)return;
  line.config=line.config||{};
  const images=productImages(main);
  line.config.product_images=images;
  line.config.product_details=productDetails(main);
  if(line.config.datasheet_enabled){
    const current=uniq(line.config.datasheet_images).filter(x=>images.includes(x)).slice(0,5);
    line.config.datasheet_images=current.length?current:images.slice(0,1);
  }
}
const previousVariant=window.hcaProductVariantData;
if(previousVariant)window.hcaProductVariantData=function(x={}){
  const v=previousVariant(x);
  return {...v,images:productImages(x),description:x.description||'',short_description:x.short_description||'',attributes:Array.isArray(x.attributes)?x.attributes:[],categories:Array.isArray(x.categories)?x.categories:[],permalink:x.permalink||''};
};
const previousSelect=window.hcaSelectMainProduct;
if(previousSelect)window.hcaSelectMainProduct=function(line,main){previousSelect(line,main);applyProductMeta(line,main)};

function customerText(c={}){
  const display=typeof businessCustomerDisplay==='function'?businessCustomerDisplay(c):[c.company_name,c.first_name,c.last_name].filter(Boolean).join(' ');
  return [c.customer_no,display].filter(Boolean).join(' · ')||c.email||'Kunde';
}
function customerHay(c={}){
  return [c.customer_no,c.company_name,c.first_name,c.last_name,c.email,c.phone,customerText(c)].join(' ').toLocaleLowerCase('de-DE');
}
function buildCustomerCombobox(){
  const select=document.querySelector('#bqCustomer');
  if(!select||select.closest('.hca137-customer-combo'))return;
  const old=select.closest('.hca136-customer-combo');
  const locked=select.disabled;
  const wrap=document.createElement('div');wrap.className='hca137-customer-combo';
  const input=document.createElement('input');input.className='text-input hca137-customer-input';input.type='text';input.autocomplete='off';input.placeholder='Kunde auswählen oder Namen eingeben …';input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-expanded','false');input.disabled=locked;
  const toggle=document.createElement('button');toggle.type='button';toggle.className='hca137-combo-toggle';toggle.setAttribute('aria-label','Kundenliste öffnen');toggle.textContent='▾';toggle.disabled=locked;
  const list=document.createElement('div');list.className='hca137-customer-list hidden';list.setAttribute('role','listbox');
  const customers=Array.isArray(window.businessCustomerCache)?businessCustomerCache:[];
  const selected=()=>customers.find(c=>String(c.id)===String(select.value));
  input.value=selected()?customerText(selected()):'';
  function close(){list.classList.add('hidden');input.setAttribute('aria-expanded','false');H137.customerOpen=false}
  function choose(c){
    select.value=String(c.id);input.value=customerText(c);close();
    select.dispatchEvent(new Event('change',{bubbles:true}));input.focus();
  }
  function render(needle=''){
    const q=String(needle||'').trim().toLocaleLowerCase('de-DE');
    const rows=customers.filter(c=>!q||customerHay(c).includes(q)).slice(0,100);
    list.innerHTML=rows.length?rows.map((c,i)=>'<button type="button" role="option" data-h137-customer="'+escapeHtml(String(c.id))+'"><b>'+escapeHtml(customerText(c))+'</b>'+(c.email?'<span>'+escapeHtml(c.email)+'</span>':'')+'</button>').join(''):'<div class="hca137-no-result">Kein Kunde gefunden</div>';
    list.querySelectorAll('[data-h137-customer]').forEach(b=>b.addEventListener('mousedown',e=>{e.preventDefault();const c=customers.find(x=>String(x.id)===String(b.dataset.h137Customer));if(c)choose(c)}));
    list.classList.remove('hidden');input.setAttribute('aria-expanded','true');H137.customerOpen=true;
  }
  input.addEventListener('focus',()=>render(input.value===customerText(selected())?'':input.value));
  input.addEventListener('input',()=>render(input.value));
  input.addEventListener('keydown',e=>{
    const buttons=[...list.querySelectorAll('[data-h137-customer]')],active=document.activeElement;
    if(e.key==='ArrowDown'){e.preventDefault();if(list.classList.contains('hidden'))render(input.value);(buttons[0]||input).focus()}
    else if(e.key==='Enter'){const exact=customers.find(c=>customerText(c).toLocaleLowerCase('de-DE')===input.value.trim().toLocaleLowerCase('de-DE'));if(exact){e.preventDefault();choose(exact)}}
    else if(e.key==='Escape'){close();input.value=selected()?customerText(selected()):''}
  });
  list.addEventListener('keydown',e=>{const buttons=[...list.querySelectorAll('[data-h137-customer]')],i=buttons.indexOf(document.activeElement);if(e.key==='ArrowDown'){e.preventDefault();buttons[Math.min(i+1,buttons.length-1)]?.focus()}else if(e.key==='ArrowUp'){e.preventDefault();if(i<=0)input.focus();else buttons[i-1]?.focus()}else if(e.key==='Enter'){e.preventDefault();document.activeElement?.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))}else if(e.key==='Escape'){close();input.focus()}});
  toggle.addEventListener('click',()=>H137.customerOpen?close():render(''));
  input.addEventListener('blur',()=>setTimeout(()=>{if(!wrap.contains(document.activeElement)){close();input.value=selected()?customerText(selected()):''}},100));
  select.classList.add('hca137-native-select');select.tabIndex=-1;
  wrap.append(input,toggle,list,select);
  if(old)old.replaceWith(wrap);else select.parentNode.appendChild(wrap);
}
const previousQuoteRender=window.renderBusinessQuoteEditor;
window.renderBusinessQuoteEditor=function(){previousQuoteRender();buildCustomerCombobox()};

function resultImage(x={}){
  const src=productImages(x)[0];
  return src?'<img class="hca137-product-thumb" src="'+escapeHtml(src)+'" alt="" loading="lazy" referrerpolicy="no-referrer">':'<span class="hca137-product-thumb empty">Kein Bild</span>';
}
window.hcaSearchMainProducts=async function(i,query,box,lines,rerender){
  query=String(query||'').trim();if(!box)return;
  if(query.length<2){box.classList.add('hidden');box.innerHTML='';return}
  box.classList.remove('hidden');box.innerHTML='<div class="business-loading compact">Hauptartikel werden gesucht …</div>';
  try{
    const res=await productionFetch('/api/hca-shared/woocommerce/products/search?q='+encodeURIComponent(query)+'&limit=100',{timeoutMs:30000}),d=await res.json();
    if(!res.ok)throw new Error(d.detail||d.error||('HTTP '+res.status));
    const mains=hcaGroupMainProducts(d.items||[]);
    box.innerHTML=mains.length?mains.map((x,n)=>'<button type="button" class="hca137-product-result" data-hca-main-product="'+n+'">'+resultImage(x)+'<span class="hca137-product-copy"><b>'+escapeHtml(x.name||'Artikel')+'</b><span>'+escapeHtml([x.sku?('Art.-Nr. '+x.sku):'',x._colors?.length?(x._colors.length+' Farbe'+(x._colors.length===1?'':'n')):'ohne Farbvarianten',x._variantCount>1?(x._variantCount+' Varianten'):''].filter(Boolean).join(' · '))+'</span></span></button>').join(''):'<div class="business-empty compact">Keine Hauptartikel gefunden.</div>';
    box._mainItems=mains;
    box.querySelectorAll('[data-hca-main-product]').forEach(b=>b.onclick=async()=>{const line=lines[Number(i)],main=mains[Number(b.dataset.hcaMainProduct)];if(!line||!main)return;hcaSelectMainProduct(line,main);applyProductMeta(line,main);if(line.product_id)try{await hca103ShopPrice(line)}catch{}rerender()});
  }catch(err){box.innerHTML='<div class="business-empty compact error">'+escapeHtml(err.message||String(err))+'</div>'}
};
window.searchBusinessQuoteProducts=(i,query)=>hcaSearchMainProducts(i,query,document.querySelector('[data-bq-results="'+i+'"]'),activeBusinessQuote?.items||[],renderBusinessQuoteEditor);
window.hca103OrderSearch=async function(i,q){
  const box=document.querySelector('[data-o-results="'+i+'"]');
  if(!box||String(q).trim().length<2){box?.classList.add('hidden');return}
  await hcaSearchMainProducts(i,q,box,HCA103.orderLines,hca103RenderOrderLines);
};
window.hca103InvoiceSearch=async function(i,q,row){
  const query=String(q||'').trim();let box=row.querySelector('.hca137-invoice-results');
  if(!box){box=document.createElement('div');box.className='business-product-search-results hca137-invoice-results hidden';row.appendChild(box)}
  if(query.length<2){box.classList.add('hidden');return}
  await hcaSearchMainProducts(i,query,box,financeInvoiceLines,renderFinanceInvoiceLines);
};

function datasheetHtml(line,i,locked){
  const cfg=line.config||{},images=uniq(cfg.product_images),enabled=!!cfg.datasheet_enabled,selected=uniq(cfg.datasheet_images);
  if(!line.product_id&&!cfg.main_product_id)return '';
  return '<div class="hca137-datasheet"><label class="hca137-datasheet-toggle"><input type="checkbox" data-h137-sheet="'+i+'" '+(enabled?'checked ':'')+(locked?'disabled':'')+'> Artikeldatenblatt als PDF an das Angebot anhängen</label>'+
    (enabled?'<div class="hca137-datasheet-images"><div><b>Produktbilder auswählen</b><small>Mindestens 1, höchstens 5 Bilder.</small></div>'+images.map((src,n)=>'<label class="'+(selected.includes(src)?'selected':'')+'"><input type="checkbox" data-h137-sheet-image="'+i+':'+n+'" '+(selected.includes(src)?'checked ':'')+(locked?'disabled':'')+'><img src="'+escapeHtml(src)+'" alt="Artikelbild '+(n+1)+'" loading="lazy"><span>Bild '+(n+1)+'</span></label>').join('')+'</div>':'')+
  '</div>';
}
const previousLineHtml=window.businessQuoteLineHtml;
window.businessQuoteLineHtml=function(line,i,locked=false){
  const html=previousLineHtml(line,i,locked),extra=datasheetHtml(line,i,locked),at=html.lastIndexOf('</article>');
  return at>=0?html.slice(0,at)+extra+html.slice(at):html+extra;
};
document.addEventListener('change',e=>{
  if(e.target?.dataset?.h137Sheet!==undefined){
    const line=activeBusinessQuote?.items?.[Number(e.target.dataset.h137Sheet)];if(!line)return;
    line.config=line.config||{};line.config.datasheet_enabled=!!e.target.checked;
    if(e.target.checked&&!uniq(line.config.datasheet_images).length)line.config.datasheet_images=uniq(line.config.product_images).slice(0,1);
    hcaEditorDirty=true;renderBusinessQuoteEditor();
  }
  if(e.target?.dataset?.h137SheetImage!==undefined){
    const [i,n]=e.target.dataset.h137SheetImage.split(':').map(Number),line=activeBusinessQuote?.items?.[i];if(!line)return;
    const images=uniq(line.config?.product_images),src=images[n],set=new Set(uniq(line.config?.datasheet_images));
    if(e.target.checked&&set.size>=5){e.target.checked=false;alert('Pro Artikeldatenblatt können höchstens fünf Bilder ausgewählt werden.');return}
    if(e.target.checked)set.add(src);else set.delete(src);
    if(!set.size){e.target.checked=true;set.add(src);alert('Bitte mindestens ein Artikelbild auswählen.')}
    line.config.datasheet_images=[...set].slice(0,5);hcaEditorDirty=true;
  }
},true);

function removeSecondSplash(){
  if(window.chrome&&window.chrome.webview){document.documentElement.classList.add('hca-native-host');document.querySelector('#hcaStartupSplash')?.remove()}
}
removeSecondSplash();
window.addEventListener('DOMContentLoaded',removeSecondSplash,{once:true});
})();
