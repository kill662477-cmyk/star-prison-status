import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,writeFile} from 'node:fs/promises';
import {resolve,extname} from 'node:path';
const root=resolve('.');
const snapshot=JSON.parse(await readFile('live/prisoners.json','utf8'));
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png','.woff2':'font/woff2','.json':'application/json'};
const server=createServer(async(req,res)=>{
  try{
    const url=new URL(req.url,'http://localhost');
    const path=url.pathname==='/data/prisoners.json'?resolve('live/prisoners.json'):resolve(root,'.'+(url.pathname==='/'?'/index.html':url.pathname));
    if(!path.startsWith(root+'/')&&!path.startsWith(root+'\\'))throw Error('Invalid path');
    res.setHeader('Content-Type',types[extname(path)]||'application/octet-stream');res.end(await readFile(path));
  }catch{res.writeHead(404);res.end();}
});
await new Promise(r=>server.listen(4178,'127.0.0.1',r));
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:720,height:900},deviceScaleFactor:1});
  await page.goto('http://127.0.0.1:4178/?capture=1&cols=3');
  await page.waitForFunction(count=>document.querySelectorAll('.prisoner').length===count&&document.querySelector('#updated').textContent!=='확인 중',snapshot.prisoners.length);
  await page.evaluate(async()=>{await document.fonts.ready;await Promise.all(['assets/mugshots-v2.png','assets/haetdik-hood-v2.png','assets/prison-wall.png'].map(src=>new Promise((resolve,reject)=>{const img=new Image();img.onload=resolve;img.onerror=reject;img.src=src;})));});
  const geometry=await page.evaluate(()=>({width:document.documentElement.clientWidth,height:document.documentElement.scrollHeight,columns:getComputedStyle(document.querySelector('.cards')).gridTemplateColumns.split(' ').length}));
  if(geometry.columns!==3)throw Error('Capture must have three columns');
  await page.screenshot({path:'live/status.jpg',type:'jpeg',quality:90,fullPage:true});
  await writeFile('live/capture.json',JSON.stringify({...geometry,count:snapshot.prisoners.length,captured_at:new Date().toISOString()},null,2));
  console.log(geometry);
}finally{await browser.close();await new Promise(r=>server.close(r));}
