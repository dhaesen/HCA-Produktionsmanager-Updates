'use strict';
const fs=require('fs');
const vm=require('vm');
let source=fs.readFileSync(__dirname+'/hca-v01327.js','utf8');
source=source.replace('\nasync function parallel(', '\nglobalThis.__hca1327References=references;\nasync function parallel(');
const sandbox={
  console,Map,Set,Promise,URL,Blob,
  productionFetch:async()=>({ok:true,blob:async()=>new Blob()}),
  hcaV123DocumentPreview:async()=>{},saveBusinessQuote:async()=>{},printBusinessQuote:async()=>{},
  document:{querySelector:()=>null,createElement:()=>({getContext:()=>({fillRect(){},drawImage(){}})})},
  alert(){},activeBusinessQuote:null,businessQuotePayload:()=>({items:[]}),hcaV123PreviewUrl:null,
};
vm.createContext(sandbox);vm.runInContext(source,sandbox);
const config={
  datasheet_images:['https://shop.test/chosen-1.webp','https://shop.test/chosen-2.webp'],
  product_images:Array.from({length:20},(_,i)=>`https://shop.test/product-${i}.webp`),
  product_details:{
    main_image:'https://shop.test/main.webp',
    gallery_images:Array.from({length:10},(_,i)=>`https://shop.test/gallery-${i}.webp`),
    color_images:Array.from({length:12},(_,i)=>({name:`Farbe ${i}`,image:`https://shop.test/color-${i}.webp`})),
  },
  wizard_config:{areas:Array.from({length:3},(_,i)=>({name:`Position ${i}`,image:`https://shop.test/area-${i}.webp`}))},
};
const refs=sandbox.__hca1327References(config);
if(refs.length!==21)throw new Error(`Erwartet 21 tatsächlich sichtbare Bilder, erhalten ${refs.length}`);
if(refs.some(row=>row.url.includes('product-')||row.url.includes('gallery-5')))throw new Error('Nicht dargestellte Bilder werden unnötig geladen');
console.log('v0.13.27 client tests: OK');
