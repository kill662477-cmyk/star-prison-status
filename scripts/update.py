"""Incremental public-board collection. State is published only after capture succeeds."""
import argparse, json, re, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

KST=timezone(timedelta(hours=9))
ROOT=Path(__file__).resolve().parent.parent
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def member(a):
    m=re.search(r"show_nick_dropdown\(this,\s*'\d+',\s*'(\d+)'",a.get('onclick','')) if a else None
    return m[1] if m else None
def fetch(url):
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; StarPrisonStatus/1.0)'}),timeout=30) as r:
                html=r.read().decode('utf-8')
            time.sleep(.3)
            return BeautifulSoup(html,'html.parser')
        except Exception:
            if attempt==2: raise
            time.sleep(2**attempt)
def parse_bans(soup,url,now):
    if not soup.select_one('[data-ban-status-root]'): raise ValueError('Missing ban page structure')
    rows=soup.select('article[data-deny-row]')
    if not rows and not re.search(r'(없습니다|없음)',soup.select_one('[data-ban-status-root]').get_text()):
        raise ValueError('Unrecognized empty ban page')
    result=[]
    for row in rows:
        spans=[x.get_text(' ',strip=True) for x in row.select('span')]
        stamp=next((x[3:] for x in spans if x.startswith('등록 ')),None)
        period=spans[1]
        remaining=next((x for x in spans if '남음' in x),None)
        if not stamp: raise ValueError('Missing registration date')
        life=bool(re.search(r'영구|무기',period))
        duration=re.search(r'(\d+)\s*(개월|주|일)',period)
        if not life and not duration: raise ValueError('Unsupported ban duration: '+period)
        end=None
        if duration:
            start=datetime.strptime(stamp,'%y-%m-%d %H:%M').replace(tzinfo=KST)
            end=start+timedelta(days=int(duration[1])*{'개월':30,'주':7,'일':1}[duration[2]])
            parts=re.findall(r'(\d+)(일|시간|분|초)',remaining or '')
            if not parts: raise ValueError('Missing remaining time')
            seconds=sum(int(n)*{'일':86400,'시간':3600,'분':60,'초':1}[u] for n,u in parts)
            if abs((end-now).total_seconds()-seconds)>3700: raise ValueError('Expiry disagrees with source')
        result.append(dict(ban_id=row['data-deny-row'],member_id=member(row.select_one('strong a[onclick]')),nickname=row.select_one('strong').get_text(strip=True),reason=row.select_one('.yg-ban-status-reason').get_text(' ',strip=True),period=period,registered_at=stamp,release_at=end.isoformat() if end else None,d_day=(end.date()-now.date()).days if end else None,life_sentence=life,remaining_raw=remaining,source_url=url))
    return result
def collect_bans(board):
    result={};previous=None
    for page in range(1,101):
        url=f'https://ygosu.com/ban_status/?view=restrictions&sort=recent&bid={board}&page={page}'
        soup=fetch(url)
        rows=parse_bans(soup,url,datetime.now(KST))
        ids=[x['ban_id'] for x in rows]
        if ids and ids==previous: raise ValueError('Ban pagination repeated')
        previous=ids
        result.update({x['ban_id']:x for x in rows})
        pages=[int(m[1]) for a in soup.select('a.yg-pagination-link[href]') if (m:=re.search(r'page=(\d+)',a['href']))]
        if not pages or page>=max(pages): return list(result.values()),page
    raise ValueError('Ban page limit reached')
def parse_posts(soup):
    table=soup.select_one('table.bd_list')
    if not table: raise ValueError('Missing prison board table')
    posts=[]
    for row in table.select('tr'):
        link=row.select_one('td.tit a[href]')
        match=re.match(r'/board/pan_prison/(\d+)',link['href']) if link else None
        if not match: continue
        a=row.select_one('td.name a[onclick]')
        posts.append(dict(post_id=int(match[1]),member_id=member(a),nickname=a.get_text(strip=True) if a else '',post_url=f'https://ygosu.com/board/pan_prison/{match[1]}',notice='notice' in row.get('class',[])))
    return posts
def collect_new(authors,checkpoint):
    high=checkpoint;previous=None
    for page in range(1,501):
        rows=parse_posts(fetch(f'https://ygosu.com/board/pan_prison/?page={page}'))
        normal=[r['post_id'] for r in rows if not r['notice']]
        for row in rows:
            if row['member_id'] and row['member_id'] not in authors:
                authors[row['member_id']]={k:v for k,v in row.items() if k!='notice'}
        if not normal: return high,page
        high=max(high,max(normal))
        if min(normal)<=checkpoint: return high,page
        if normal==previous: return high,page
        previous=normal
    raise ValueError('Incremental page limit reached; checkpoint not advanced')
def eligible(bans,prison_bans,authors,overrides):
    blocked={x['member_id'] for x in prison_bans if x['member_id']}
    blocked_names={x['nickname'] for x in prison_bans if not x['member_id']}
    included={};excluded=[];pending=[]
    for ban in bans:
        mid=ban['member_id']
        if not mid or ban['nickname'] in blocked_names:
            pending.append(ban);continue
        if mid not in authors: continue
        if mid in blocked: excluded.append(ban);continue
        included[mid]=dict(ban,prison_evidence=authors[mid])
    for override in overrides:
        # Explicit owner override wins over automatic rules; visibly labelled.
        included[override['member_id']]=dict(override,manual_override=True)
    return sorted(included.values(),key=lambda x:x['registered_at'],reverse=True),excluded,pending
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--state-dir',default='live');args=parser.parse_args()
    directory=ROOT/args.state_dir
    source=directory if (directory/'state.json').exists() else ROOT/'seed'
    state=read(source/'state.json');authors={x['member_id']:x for x in read(source/'authors.json')}
    checkpoint,pages=collect_new(authors,state['last_post_id'])
    bans,ban_pages=collect_bans('pan_monstarz');prison_bans,prison_pages=collect_bans('pan_prison')
    records,excluded,pending=eligible(bans,prison_bans,authors,read(ROOT/'data/manual-overrides.json'))
    now=datetime.now(KST).isoformat()
    snapshot=dict(collected_at=now,prisoners=records,match_count=len(records),ban_count=len(bans),ban_pages=ban_pages,prison_board_ban_count=len(prison_bans),prison_board_ban_pages=prison_pages,incremental_pages=pages,author_count=len(authors),excluded_prison_banned=excluded,missing_member_id_bans=pending,manual_count=sum(bool(x.get('manual_override')) for x in records))
    write(directory/'prisoners.json',snapshot);write(directory/'authors.json',list(authors.values()))
    write(directory/'state.json',dict(last_post_id=checkpoint,last_success=now))
    print(json.dumps({k:v for k,v in snapshot.items() if not isinstance(v,list)},ensure_ascii=False))
if __name__=='__main__': main()
