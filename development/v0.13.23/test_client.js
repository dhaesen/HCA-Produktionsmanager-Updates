const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync(__dirname+'/hca-v01323.js','utf8');

function element(tag='div'){
  return {tag,dataset:{},children:[],innerHTML:'',className:'',
    append(x){this.children.push(x)},prepend(x){this.children.unshift(x)},
    querySelector(selector){
      if(selector==='[data-hca1323-optional]')return this.input||null;
      if(selector==='.business-quote-line-head .actions-row')return this.actions||null;
      if(selector==='.business-quote-line-head')return this.head||null;
      return null;
    }};
}

let baseRender=0;
const line={item_type:'product',config:{production_steps:[{technique:'laser'}]}};
const input={checked:false,listeners:{},addEventListener(type,fn){this.listeners[type]=fn}};
const actions=element();
const head=element();
const card=element();card.dataset.bqLine='0';card.actions=actions;card.head=head;
const sandbox={
  window:null,console,
  activeBusinessQuote:{status:'draft',items:[line]},
  hcaEditorDirty:false,
  syncBusinessQuoteHeader(){},
  renderBusinessQuoteEditor(){baseRender++},
  document:{
    querySelectorAll(){return [card]},
    createElement(){const holder=element();holder.input=input;return holder}
  }
};
sandbox.window=sandbox;
vm.createContext(sandbox);vm.runInContext(source,sandbox);
if(actions.children.length!==1)throw new Error('Optional-Schalter wurde nicht eingesetzt');
input.checked=true;input.listeners.change();
if(line.item_type!=='optional')throw new Error('Position wurde nicht optional');
if(line.config.production_steps.length!==1)throw new Error('Veredelung ging beim Umschalten verloren');
if(!sandbox.hcaEditorDirty||baseRender!==1)throw new Error('Editor wurde nach Umschaltung nicht aktualisiert');
input.checked=false;input.listeners.change();
if(line.item_type!=='product')throw new Error('Optionale Position konnte nicht zurückgestellt werden');
console.log('v0.13.23 client regression test passed');
