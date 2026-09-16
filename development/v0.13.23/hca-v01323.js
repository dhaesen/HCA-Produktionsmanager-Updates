/* HCA v0.13.23 · bestehende Angebotspositionen nachträglich optional schalten */
(()=>{
'use strict';

const isOptional=line=>String(line?.item_type||'product').toLowerCase()==='optional';
const isText=line=>String(line?.item_type||'product').toLowerCase()==='text';
const quoteLocked=()=>['accepted','rejected','expired'].includes(String(activeBusinessQuote?.status||'').toLowerCase());

function optionalToggleHtml(index,line,locked){
  const checked=isOptional(line)?' checked':'';
  const disabled=locked?' disabled':'';
  return `<label class="hca1323-optional-toggle" title="Optionale Positionen werden nicht in die Angebotssumme eingerechnet"><input type="checkbox" data-hca1323-optional="${index}"${checked}${disabled}><span>Optional</span></label>`;
}

function installOptionalToggles(){
  if(!activeBusinessQuote)return;
  const locked=quoteLocked();
  document.querySelectorAll('#businessQuoteLines [data-bq-line]').forEach(card=>{
    const index=Number(card.dataset.bqLine);
    const line=activeBusinessQuote.items?.[index];
    if(!line||isText(line)||card.querySelector('[data-hca1323-optional]'))return;
    const actions=card.querySelector('.business-quote-line-head .actions-row');
    const head=card.querySelector('.business-quote-line-head');
    if(!head)return;
    const holder=document.createElement('div');
    holder.className='hca1323-optional-holder';
    holder.innerHTML=optionalToggleHtml(index,line,locked);
    if(actions)actions.prepend(holder);
    else head.append(holder);
    const input=holder.querySelector('[data-hca1323-optional]');
    if(!input||locked)return;
    input.addEventListener('change',()=>{
      if(typeof syncBusinessQuoteHeader==='function')syncBusinessQuoteHeader();
      const current=activeBusinessQuote?.items?.[index];
      if(!current||isText(current))return;
      current.item_type=input.checked?'optional':'product';
      current.config=current.config||{};
      current.config.hca_optional_position=input.checked;
      if(typeof hcaEditorDirty!=='undefined')hcaEditorDirty=true;
      window.renderBusinessQuoteEditor();
    });
  });
}

const previousRender=window.renderBusinessQuoteEditor;
window.renderBusinessQuoteEditor=function(){
  const result=previousRender.apply(this,arguments);
  installOptionalToggles();
  return result;
};

installOptionalToggles();
window.hca1323={installOptionalToggles,isOptional};
})();
