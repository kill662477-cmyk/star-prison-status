"""Validate extracted snapshot and write a reviewable Korean report."""
import json, re
from datetime import datetime
from collect_data import ROOT, RAW, KST, add_release, save, fetch, member

def main():
    snapshot=json.loads((ROOT/'data/prisoners.json').read_text(encoding='utf-8'))
    bans=json.loads((ROOT/'data/bans.json').read_text(encoding='utf-8'))
    now=datetime.now(KST)
    for b in bans:
        p=re.search(r'page=(\d+)',b['source_url'])[1]
        b['observed_at']=datetime.fromtimestamp((RAW/f'bans-{p}.html').stat().st_mtime,KST).isoformat()
        add_release(b,now)
    by_id={b['ban_id']:b for b in bans}
    prison_bans=[]
    page=1
    while True:
        url=f'https://ygosu.com/ban_status/?bid=pan_prison&view=restrictions&sort=recent&page={page}'
        s=fetch(url,f'prison-bans-{page}.html')
        for row in s.select('article[data-deny-row]'):
            a=row.select_one('strong a[onclick]')
            prison_bans.append(dict(member_id=member(a),nickname=row.select_one('strong').get_text(strip=True),reason=row.select_one('.yg-ban-status-reason').get_text(' ',strip=True),source_url=url,ban_id=row['data-deny-row']))
        pages=[int(m[1]) for a in s.select('a.yg-pagination-link[href]') if (m:=re.search(r'page=(\d+)',a['href']))]
        if not pages or page>=max(pages):
            break
        page+=1
    blocked={b['member_id']:b for b in prison_bans if b['member_id']}
    save('prison-board-bans.json',prison_bans)
    authors=json.loads((ROOT/'data/prison-authors.json').read_text(encoding='utf-8'))
    author_map={a['member_id']:a for a in authors}
    candidates=[dict(b,prison_evidence=author_map[b['member_id']]) for b in bans if b['member_id'] in author_map]
    snapshot['excluded_prison_banned']=[dict(b,exclusion_evidence=blocked[b['member_id']]) for b in candidates if b['member_id'] in blocked]
    snapshot['prisoners']=[b for b in candidates if b['member_id'] not in blocked]
    snapshot['match_count']=len(snapshot['prisoners'])
    snapshot['prison_board_ban_count']=len(prison_bans)
    snapshot['eligibility_rule']='현재 스타대학 밴 AND 공개 스타감옥 작성 이력 AND 현재 스타감옥 밴 아님'
    for b in snapshot['prisoners']:
        b.update(by_id[b['ban_id']])
        assert b['member_id']==b['prison_evidence']['member_id']
        assert b['prison_evidence']['post_url'].startswith('https://ygosu.com/board/pan_prison/')
        assert b['remaining_crosscheck_within_1h']
    snapshot['d_day_as_of']=now.isoformat()
    snapshot['missing_member_id_bans']=[b for b in bans if b['member_id'] is None]
    snapshot['release_date_note']='등록일 + 기간으로 계산. 1개월=30일, 1주=7일. 원본 남은 시간과 1시간 이내 일치 검증. 등록시각 분 단위, D-day 한국시간 날짜 기준.'
    save('bans.json',bans)
    save('prisoners.json',snapshot)
    lines=['# 스타감옥 죄수현황 — 실제 데이터 추출', '',
           f"집계: {now:%Y-%m-%d %H:%M} KST. 수집 중 변경 가능성이 있는 시점별 스냅샷.", '',
           f"- 현재 스타대학 밴: {len(bans)}건 ({snapshot['ban_pages']}페이지).",
           f"- 스타감옥 확인: {snapshot['prison_pages']}페이지, 작성자 {len(authors)}명.",
           f"- 조회 가능한 과거 목록 끝 도달: {'예' if snapshot['history_complete'] else '아니오'}.",
           f"- 회원번호 일치 수감자: {len(snapshot['prisoners'])}명.",
           f"- 스타감옥 밴 목록 {len(prison_bans)}건 대조, 후보 중 {len(snapshot['excluded_prison_banned'])}명 제외.",
           f"- 밴 목록 회원번호 미노출: {len(snapshot['missing_member_id_bans'])}건. 자동 대조 보류.", '',
           '| 닉네임 (회원번호) | 밴사유 원문 | 수감기간 | 출소 예정 (KST) | D-day | 작성 증거 |',
           '|---|---|---|---|---|---|']
    for b in snapshot['prisoners']:
        esc=lambda s:s.replace('|','\\|').replace('\n',' ')
        end=datetime.fromisoformat(b['release_at'])
        day='D-DAY' if b['d_day']==0 else f"D-{b['d_day']}"
        lines.append(f"| {esc(b['nickname'])} ({b['member_id']}) | {esc(b['reason'])} | {b['registered_at']} / {b['period']} | {end:%Y-%m-%d %H:%M} | {day} | [스타감옥 글]({b['prison_evidence']['post_url']}) |")
    lines += ['', '스타감옥 밴으로 제외: '+', '.join(f"{b['nickname']} ({b['member_id']})" for b in snapshot['excluded_prison_banned']), '', snapshot['release_date_note'], '',
              '주의: 삭제·비공개 글은 확인 불가. 공지 중 다른 게시판 글은 제외. 댓글 작성만으로는 포함하지 않음. 작성자 증거는 확인한 글 하나이며 최초 작성일을 뜻하지 않음.', '',
              '추출 스크립트는 이번 조사용이며 저장 HTML을 재사용함. 매시간 운영용 수집·배포·이미지 갱신은 아직 구현하지 않음.', '',
              '[밴 목록](https://ygosu.com/ban_status/?view=restrictions&sort=recent&bid=pan_monstarz&page=1) · [스타감옥](https://ygosu.com/board/pan_prison)', '']
    (ROOT/'data/report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'matched':len(snapshot['prisoners']),'complete':snapshot['history_complete'],'crosschecks':sum(b.get('remaining_crosscheck_within_1h',False) for b in bans),'bans':len(bans)},ensure_ascii=False))

if __name__=='__main__':
    main()
