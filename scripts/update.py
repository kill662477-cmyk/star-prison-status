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
        date=row.select_one('td.date')
        posts.append(dict(post_id=int(match[1]),member_id=member(a),nickname=a.get_text(strip=True) if a else '',post_url=f'https://ygosu.com/board/pan_prison/{match[1]}',date_raw=date.get_text(strip=True) if date else '',notice='notice' in row.get('class',[])))
    return posts
def post_time(raw,now):
    """List rows show today's posts as HH:MM and older ones as YY.MM.DD."""
    raw=(raw or '').strip()
    if re.fullmatch(r'\d{1,2}:\d{2}',raw):
        hour,minute=raw.split(':')
        return now.replace(hour=int(hour),minute=int(minute),second=0,microsecond=0),True
    if re.fullmatch(r'\d{2}\.\d{2}\.\d{2}',raw):
        return datetime.strptime(raw,'%y.%m.%d').replace(tzinfo=KST),False
    raise ValueError('Unsupported post date: '+raw)
def ban_time(stamp):
    for fmt in ('%y-%m-%d %H:%M','%y-%m-%d'):
        try: return datetime.strptime(stamp,fmt).replace(tzinfo=KST)
        except ValueError: pass
    raise ValueError('Unsupported ban date: '+str(stamp))
def resolve_exact(entry):
    """List pages only date older posts, so read the exact stamp off the post itself."""
    element=fetch(entry['post_url']).select_one('.board_top .date')
    found=re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',element.get_text(' ',strip=True) if element else '')
    if not found: raise ValueError('Missing exact post time: '+entry['post_url'])
    entry['posted_at']=datetime.strptime(found[0],'%Y-%m-%d %H:%M:%S').replace(tzinfo=KST).isoformat()
    entry['posted_exact']=True
    return entry
def collect_new(authors,checkpoint,floor,now):
    """Walk back to the oldest ban so every author's latest post is known."""
    high=checkpoint;previous=None
    for page in range(1,501):
        rows=parse_posts(fetch(f'https://ygosu.com/board/pan_prison/?page={page}'))
        normal=[r for r in rows if not r['notice']]
        for row in normal:
            if not row['member_id']: continue
            stamp,exact=post_time(row['date_raw'],now)
            known=authors.get(row['member_id'])
            if known and known.get('post_id',0)>row['post_id']: continue
            authors[row['member_id']]=dict({k:v for k,v in row.items() if k!='notice'},posted_at=stamp.isoformat(),posted_exact=exact)
        ids=[r['post_id'] for r in normal]
        if not ids: return high,page
        high=max(high,max(ids))
        if min(post_time(r['date_raw'],now)[0] for r in normal)<floor: return high,page
        if ids==previous: return high,page
        previous=ids
    raise ValueError('Scan page limit reached; ban window not covered')
def posted_after_ban(entry,ban):
    """Only members who posted in the prison board after their ban was registered."""
    if not entry or not entry.get('posted_at'): return False
    posted=datetime.fromisoformat(entry['posted_at']);banned=ban_time(ban['registered_at'])
    return posted>banned if entry.get('posted_exact') else posted.date()>banned.date()
def eligible(bans,prison_bans,authors,overrides):
    blocked={x['member_id'] for x in prison_bans if x['member_id']}
    blocked_names={x['nickname'] for x in prison_bans if not x['member_id']}
    included={};excluded=[];pending=[]
    for ban in bans:
        mid=ban['member_id']
        if not mid or ban['nickname'] in blocked_names:
            pending.append(ban);continue
        if not posted_after_ban(authors.get(mid),ban): continue
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
    stamp=datetime.now(KST)
    bans,ban_pages=collect_bans('pan_monstarz');prison_bans,prison_pages=collect_bans('pan_prison')
    floor=min([ban_time(x['registered_at']) for x in bans],default=stamp)-timedelta(days=1)
    checkpoint,pages=collect_new(authors,state['last_post_id'],floor,stamp)
    for ban in bans:
        # A same-day list entry cannot be ordered against the ban without the exact stamp.
        entry=authors.get(ban['member_id'] or '')
        if entry and entry.get('posted_at') and not entry.get('posted_exact') and datetime.fromisoformat(entry['posted_at']).date()==ban_time(ban['registered_at']).date():
            resolve_exact(entry)
    records,excluded,pending=eligible(bans,prison_bans,authors,read(ROOT/'data/manual-overrides.json'))
    now=stamp.isoformat()
    snapshot=dict(collected_at=now,prisoners=records,match_count=len(records),ban_count=len(bans),ban_pages=ban_pages,prison_board_ban_count=len(prison_bans),prison_board_ban_pages=prison_pages,incremental_pages=pages,scan_floor=floor.isoformat(),author_count=len(authors),excluded_prison_banned=excluded,missing_member_id_bans=pending,manual_count=sum(bool(x.get('manual_override')) for x in records))
    write(directory/'prisoners.json',snapshot);write(directory/'authors.json',list(authors.values()))
    write(directory/'state.json',dict(last_post_id=checkpoint,last_success=now))
    print(json.dumps({k:v for k,v in snapshot.items() if not isinstance(v,list)},ensure_ascii=False))
if __name__=='__main__': main()
