"""Read-only Ygosu extraction. No website publishing or account actions."""
import json, re, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).parent
RAW = ROOT / 'data' / 'raw'
KST = timezone(timedelta(hours=9))
def fetch(url, name):
    path = RAW / name
    if path.exists():
        return BeautifulSoup(path.read_text(encoding='utf-8-sig'), 'html.parser')
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as r:
        html = r.read().decode('utf-8')
    path.write_text(html, encoding='utf-8')
    time.sleep(0.35)
    return BeautifulSoup(html, 'html.parser')

def member(a):
    if a is None:
        return None
    m = re.search(r"show_nick_dropdown\(this,\s*'\d+',\s*'(\d+)'", a.get('onclick', ''))
    return m.group(1) if m else None

def save(name, data):
    (ROOT / 'data' / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def add_release(b, now):
    units = {'일': 1, '주': 7, '개월': 30}
    m = re.search(r'(\d+)\s*(개월|주|일)', b['period'])
    if not m or not b['registered_at']:
        return
    start = datetime.strptime(b['registered_at'], '%y-%m-%d %H:%M').replace(tzinfo=KST)
    end = start + timedelta(days=int(m[1]) * units[m[2]])
    b.update(release_at=end.isoformat(), d_day=(end.date()-now.date()).days,
             release_calculation='registration + duration; 1 month = 30 days; minute precision')
    parts = re.findall(r'(\d+)(일|시간|분|초)', b['remaining_raw'] or '')
    if parts:
        factors = {'일':86400, '시간':3600, '분':60, '초':1}
        displayed_seconds = sum(int(n)*factors[u] for n,u in parts)
        observed = datetime.fromisoformat(b.get('observed_at',now.isoformat()))
        b['remaining_crosscheck_within_1h'] = abs((end-observed).total_seconds()-displayed_seconds) <= 3600

def prison_pages():
    # Small bounded batches; at most three requests in flight.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for base in range(1, 2001, 10):
            pages = range(base, min(base+10, 2001))
            results = list(pool.map(lambda p: fetch(f'https://ygosu.com/board/pan_prison/?page={p}', f'prison-{p}.html'), pages))
            yield from zip(pages, results)

def main():
    now = datetime.now(KST)
    bans = {}
    page = 1
    while True:
        url = f'https://ygosu.com/ban_status/?view=restrictions&search=&sort=recent&bid=pan_monstarz&page={page}'
        s = fetch(url, f'bans-{page}.html')
        rows = s.select('article[data-deny-row]')
        if not rows:
            raise RuntimeError(f'Unexpected empty ban page {page}')
        for row in rows:
            a = row.select_one('strong a[onclick]')
            spans = [x.get_text(' ', strip=True) for x in row.select('span')]
            registered = next((x.removeprefix('등록 ') for x in spans if x.startswith('등록 ')), None)
            remaining = next((x for x in spans if '남음' in x), None)
            bans[row['data-deny-row']] = dict(ban_id=row['data-deny-row'], member_id=member(a), nickname=row.select_one('strong').get_text(strip=True), reason=row.select_one('.yg-ban-status-reason').get_text(' ',strip=True), period=spans[1], registered_at=registered, remaining_raw=remaining, release_at=None, d_day=None, source_url=url, raw_text=row.get_text(' ',strip=True))
        pages = [int(m.group(1)) for a in s.select('a.yg-pagination-link[href]') if (m:=re.search(r'page=(\d+)',a['href']))]
        print(f'Ban page {page}: {len(bans)} records', flush=True)
        if not pages or page >= max(pages):
            break
        page += 1
    for b in bans.values():
        source_page = re.search(r'page=(\d+)', b['source_url'])[1]
        b['observed_at'] = datetime.fromtimestamp((RAW / f'bans-{source_page}.html').stat().st_mtime,KST).isoformat()
        add_release(b, now)
    save('bans.json',list(bans.values()))
    evidence = {}
    scanned = 0
    complete = False
    previous = None
    for p, s in prison_pages():
        url = f'https://ygosu.com/board/pan_prison/?page={p}'
        table = s.select_one('table.bd_list')
        if table is None:
            raise RuntimeError(f'Missing board table page {p}')
        ids=[]
        for row in table.select('tr'):
            a = row.select_one('td.name a[onclick]')
            link = row.select_one('td.tit a[href]')
            if not a or not link or not re.match(r'/board/pan_prison/\d+',link['href']):
                continue
            mid=member(a)
            if not mid:
                continue
            post_url='https://ygosu.com'+link['href'].split('?')[0].rstrip('/')
            if 'notice' not in row.get('class',[]):
                ids.append(post_url)
            evidence.setdefault(mid,dict(member_id=mid,nickname=a.get_text(strip=True),post_url=post_url,date_raw=row.select_one('td.date').get_text(strip=True),list_url=url))
        scanned=p
        if not ids:
            complete=True
            break
        if ids==previous:
            # Site clamps out-of-range pages to its final page.
            complete=True
            scanned=p-1
            break
        previous=ids
        if p%10==0:
            print(f'Prison page {p}: {len(evidence)} authors, {sum(b["member_id"] in evidence for b in bans.values())} matching bans',flush=True)
    matched=[]
    for b in bans.values():
        if b['member_id'] in evidence:
            matched.append(dict(b,prison_evidence=evidence[b['member_id']]))
    matched.sort(key=lambda b:b['registered_at'] or '',reverse=True)
    save('prison-authors.json',list(evidence.values()))
    save('prisoners.json',dict(collected_at=now.isoformat(),ban_pages=page,ban_count=len(bans),prison_pages=scanned,history_complete=complete,match_count=len(matched),unmatched_status='unconfirmed; historical scan incomplete' if not complete else 'no visible post found',release_date_note='Calculated from registration + duration (1 month = 30 days), crosschecked against displayed remaining hours. Source registration has minute precision.',prisoners=matched))
    print(json.dumps(dict(bans=len(bans),authors=len(evidence),matched=len(matched),history_complete=complete),ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
