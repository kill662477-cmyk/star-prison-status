import importlib.util
import unittest
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
spec=importlib.util.spec_from_file_location('update',Path(__file__).parents[1]/'scripts/update.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
class UpdateTests(unittest.TestCase):
    def posted(self,stamp,exact=True): return dict(posted_at=stamp,posted_exact=exact)
    def test_manual_override_and_exclusion(self):
        bans=[dict(member_id='1',nickname='a',registered_at='26-09-01'),dict(member_id='2',nickname='b',registered_at='26-09-02'),dict(member_id=None,nickname='c',registered_at='26-09-03')]
        authors={'1':self.posted('2026-09-02T10:00:00+09:00'),'2':self.posted('2026-09-03T10:00:00+09:00')}
        result,excluded,pending=u.eligible(bans,[dict(member_id='2',nickname='b')],authors,[dict(member_id='3',nickname='manual',registered_at='26-09-04',life_sentence=True)])
        self.assertEqual([r['member_id'] for r in result],['3','1'])
        self.assertEqual([r['member_id'] for r in excluded],['2'])
        self.assertEqual(len(pending),1)
    def test_only_posts_after_the_ban_qualify(self):
        ban=dict(member_id='1',nickname='a',registered_at='26-09-08 23:51')
        after=self.posted('2026-09-09T00:10:00+09:00');before=self.posted('2026-09-08T18:00:00+09:00')
        self.assertTrue(u.posted_after_ban(after,ban))
        self.assertFalse(u.posted_after_ban(before,ban))
        self.assertFalse(u.posted_after_ban(None,ban))
        self.assertFalse(u.posted_after_ban({},ban))
        result,_,_=u.eligible([ban],[],{'1':before},[])
        self.assertEqual(result,[])
        result,_,_=u.eligible([ban],[],{'1':after},[])
        self.assertEqual([r['member_id'] for r in result],['1'])
    def test_same_day_list_date_never_counts_as_after(self):
        # A YY.MM.DD row carries no clock, so the day must strictly beat the ban day.
        ban=dict(member_id='1',nickname='a',registered_at='26-09-08 00:05')
        self.assertFalse(u.posted_after_ban(self.posted('2026-09-08T00:00:00+09:00',exact=False),ban))
        self.assertTrue(u.posted_after_ban(self.posted('2026-09-09T00:00:00+09:00',exact=False),ban))
    def test_post_time_reads_both_list_formats(self):
        now=datetime(2026,9,11,7,30,tzinfo=u.KST)
        self.assertEqual(u.post_time('20:18',now),(datetime(2026,9,11,20,18,tzinfo=u.KST),True))
        self.assertEqual(u.post_time('26.09.05',now),(datetime(2026,9,5,tzinfo=u.KST),False))
        with self.assertRaises(ValueError):u.post_time('',now)
    def test_month_is_30_days(self):
        html="""<div data-ban-status-root><article data-deny-row="1"><span>스타대학</span><span>징역 1개월</span><strong><a onclick="YG_COMMON.show_nick_dropdown(this, '0', '7', 'N', 'N')">닉</a></strong><p class="yg-ban-status-reason">사유</p><span>등록 26-08-31 12:00</span><span>29일 12시간 남음</span></article></div>"""
        row=u.parse_bans(BeautifulSoup(html,'html.parser'),'test',datetime(2026,9,1,tzinfo=u.KST))[0]
        self.assertEqual(row['release_at'],'2026-09-30T12:00:00+09:00')
    def test_bad_page_fails(self):
        with self.assertRaises(ValueError):u.parse_bans(BeautifulSoup('<html>error</html>','html.parser'),'test',datetime.now(u.KST))
    def test_scan_stops_at_ban_window_and_retains_authors(self):
        old=u.fetch;calls=[]
        html="""<table class="bd_list"><tr><td class="tit"><a href="/board/pan_prison/102">new</a></td><td class="name"><a onclick="YG_COMMON.show_nick_dropdown(this, '0', '8', 'N', 'N')">new name</a></td><td class="date">26.09.01</td></tr><tr><td class="tit"><a href="/board/pan_prison/100">old</a></td><td class="date">26.09.01</td></tr></table>"""
        def fake(url):calls.append(url);return BeautifulSoup(html,'html.parser')
        u.fetch=fake
        try:
            authors={'7':dict(member_id='7',nickname='old')}
            now=datetime(2026,9,11,7,30,tzinfo=u.KST)
            high,pages=u.collect_new(authors,100,datetime(2026,9,5,tzinfo=u.KST),now)
            self.assertEqual((high,pages),(102,1));self.assertEqual(set(authors),{'7','8'});self.assertEqual(len(calls),1)
            self.assertEqual(authors['8']['posted_at'],'2026-09-01T00:00:00+09:00')
            self.assertFalse(authors['8']['posted_exact'])
            self.assertIsNone(authors['7'].get('posted_at'))
        finally:u.fetch=old
    def test_scan_keeps_the_newest_post_per_member(self):
        old=u.fetch
        author = "<td class=\"name\"><a onclick=\"YG_COMMON.show_nick_dropdown(this, '0', '8', 'N', 'N')\">n</a></td>"
        pages={1:"<tr><td class=\"tit\"><a href=\"/board/pan_prison/300\">a</a></td>"+author+"<td class=\"date\">09:00</td></tr>",
               2:"<tr><td class=\"tit\"><a href=\"/board/pan_prison/200\">b</a></td>"+author+"<td class=\"date\">26.09.01</td></tr>"}
        def fake(url):
            page=int(url.rsplit('=',1)[1])
            return BeautifulSoup('<table class="bd_list">'+pages[page]+'</table>','html.parser')
        u.fetch=fake
        try:
            authors={}
            now=datetime(2026,9,11,7,30,tzinfo=u.KST)
            high,scanned=u.collect_new(authors,0,datetime(2026,9,5,tzinfo=u.KST),now)
            self.assertEqual((high,scanned),(300,2))
            self.assertEqual(authors['8']['post_id'],300)
            self.assertEqual(authors['8']['posted_at'],'2026-09-11T09:00:00+09:00')
        finally:u.fetch=old
if __name__=='__main__':unittest.main()
