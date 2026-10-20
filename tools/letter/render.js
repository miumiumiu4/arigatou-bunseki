// 手紙の型を PDF にする。node render.js 出力.pdf [差し込み.json]（json なしなら空欄の型）
const {chromium}=require('playwright');const fs=require('fs');const path=require('path');
(async()=>{const [out,data]=process.argv.slice(2);const vals=data?JSON.parse(fs.readFileSync(data,'utf8')):{};
let h=fs.readFileSync(path.join(__dirname,'letter_template.html'),'utf8').replace(/\{\{(.+?)\}\}/g,(_,k)=>vals[k]||'');
const tmp=path.join(__dirname,'.render.html');fs.writeFileSync(tmp,h);
const b=await chromium.launch({executablePath:'/opt/pw-browsers/chromium'});const p=await b.newPage();
await p.goto('file://'+tmp,{waitUntil:'networkidle'});await p.evaluate(()=>document.fonts.ready);
await p.pdf({path:out,format:'A4',printBackground:true,preferCSSPageSize:true});await b.close();fs.unlinkSync(tmp);})();
