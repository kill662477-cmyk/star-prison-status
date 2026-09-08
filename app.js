const $ = (selector) => document.querySelector(selector);
const query = new URLSearchParams(location.search);
const capture = query.get('capture') === '1';
document.body.classList.toggle('capture', capture);
document.body.classList.toggle('preview', query.get('preview') === '1');
let columns = ['3', '4', '5'].includes(query.get('cols')) ? query.get('cols') : '3';
let snapshot;
let onlySoon = false;
const portraitAssignments = { '702393':0, '697444':4, '648789':6, '656646':8, '384754':11, '697789':13, '410394':18 };
function setColumns(value) {
  columns = value;
  document.documentElement.style.setProperty('--columns', value);
  document.body.dataset.cols = value;
  document.querySelectorAll('[data-cols]').forEach(button => { if(button.tagName === 'BUTTON') button.setAttribute('aria-pressed', String(button.dataset.cols === value)); });
  $('.preview-tools>a').href = `?capture=1&cols=${value}`;
}
document.querySelectorAll('button[data-cols]').forEach(button => button.addEventListener('click', () => setColumns(button.dataset.cols)));
setColumns(columns);
function text(tag, className, value) { const el = document.createElement(tag); el.className=className; el.textContent=value; return el; }
function kstDate(value) { return new Date(value).toLocaleDateString('sv-SE',{timeZone:'Asia/Seoul'}); }
function remaining(person) {
  if(!person.release_at) return null;
  // Keep D-day consistent with the snapshot and its matching screenshot.
  return Math.round((Date.parse(kstDate(person.release_at))-Date.parse(kstDate(snapshot.collected_at)))/86400000);
}
function card(person, index) {
  const days=remaining(person);
  const el=text('article',`prisoner${days !== null && days>=0 && days<=7?' soon':''}`,'');
  const head=text('div','file-head','');
  head.append(text('span','',person.manual_override?'수동 지정':'수감기록 '+String(index+1).padStart(2,'0')),text('b','',person.life_sentence?'무기수':days !== null && days>=0 && days<=7?'출소 임박':'수감 중'));
  const image=text('div','portrait-wrap','');
  const photo=text('div','portrait','');
  const slot=portraitAssignments[person.member_id]??Number(person.member_id)%20;
  photo.style.setProperty('--x',`${slot%5*25}%`);photo.style.setProperty('--y',`${Math.floor(slot/5)*100/3}%`);
  image.setAttribute('role','img');image.setAttribute('aria-label','가상 인물 머그샷');image.append(photo);
  const content=text('div','card-content','');
  const identity=text('div','identity','');identity.append(text('h3','',person.nickname),text('span','member',`(${person.member_id})`));
  const dl=text('dl','sentence','');
  dl.append(text('dt','','수감기간'),text('dd','duration',person.period.replace('🔒 징역 ','').trim()),text('dt','',person.manual_override?'지정일':'입소일'),text('dd','',person.registered_at));
  content.append(identity,text('p','reason-label','수감사유'),text('p','reason',person.reason),dl);
  const release=text('div','release','');const date=text('div','','');date.append(text('span','','출소 예정'));
  const time=text('time','',person.life_sentence?'출소일 없음':person.release_at?kstDate(person.release_at).replaceAll('-','.'):'미확인');
  if(person.release_at){time.dateTime=person.release_at;time.append(text('span','clock',new Date(person.release_at).toLocaleTimeString('en-GB',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit'})));}
  date.append(time);release.append(date,text('strong','countdown',person.life_sentence?'무기수':days===null?'—':days===0?'D-DAY':days<0?'해제 확인 중':`D-${days}`));
  el.append(head,image,content,release);return el;
}
function render() {
  if(!snapshot) return;
  const search=$('#search').value.trim().toLocaleLowerCase();
  let records=snapshot.prisoners.filter(p=>(!onlySoon||(remaining(p)!==null&&remaining(p)>=0&&remaining(p)<=7))&&(!search||p.nickname.toLocaleLowerCase().includes(search)||p.member_id.includes(search)));
  records.sort((a,b)=>$('#sort').value==='release'?(Date.parse(a.release_at)||Infinity)-(Date.parse(b.release_at)||Infinity):b.registered_at.localeCompare(a.registered_at));
  $('#cards').replaceChildren(...records.map(card));
  if(!records.length) $('#cards').append(text('p','empty','조건에 맞는 수감자가 없습니다.'));
  $('#result-count').textContent=`전체 ${snapshot.prisoners.length}명 중 ${records.length}명 표시`;
}
$('#search').addEventListener('input',render);$('#sort').addEventListener('change',render);
for(const [id,value] of [['all-filter',false],['soon-filter',true]]) $('#'+id).addEventListener('click',()=>{onlySoon=value;for(const [key,selected] of [['all-filter',!value],['soon-filter',value]]) {$('#'+key).classList.toggle('active',selected);$('#'+key).setAttribute('aria-pressed',String(selected));}render();});
fetch('data/prisoners.json').then(response=>{if(!response.ok)throw new Error('Data unavailable');return response.json();}).then(data=>{
  if(!Array.isArray(data.prisoners))throw new Error('Invalid snapshot');snapshot=data;
  $('#total').textContent=String(data.prisoners.length).padStart(2,'0');$('#all-count').textContent=data.prisoners.length;
  $('#soon-count').textContent=data.prisoners.filter(p=>remaining(p)!==null&&remaining(p)>=0&&remaining(p)<=7).length;
  $('#updated').textContent=new Date(data.collected_at).toLocaleString('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).replaceAll('-','.');
  render();
}).catch(()=>{$('#cards').replaceChildren(text('p','empty','수감 기록을 불러오지 못했습니다. 잠시 후 새로고침해 주세요.'));$('#updated').textContent='불러오기 실패';});
