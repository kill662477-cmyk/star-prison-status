import importlib.util
import unittest
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
spec=importlib.util.spec_from_file_location('update',Path(__file__).parents[1]/'scripts/update.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
class UpdateTests(unittest.TestCase):
    def test_manual_override_and_exclusion(self):
        bans=[dict(member_id='1',nickname='a',registered_at='26-09-01'),dict(member_id='2',nickname='b',registered_at='26-09-02'),dict(member_id=None,nickname='c',registered_at='26-09-03')]
        result,excluded,pending=u.eligible(bans,[dict(member_id='2',nickname='b')],{'1':{},'2':{}},[dict(member_id='3',nickname='manual',registered_at='26-09-04',life_sentence=True)])
        self.assertEqual([r['member_id'] for r in result],['3','1'])
        self.assertEqual([r['member_id'] for r in excluded],['2'])
        self.assertEqual(len(pending),1)
    def test_month_is_30_days(self):
        html="""<div data-ban-status-root><article data-deny-row="1"><span>스타대학</span><span>징역 1개월</span><strong><a onclick="YG_COMMON.show_nick_dropdown(this, '0', '7', 'N', 'N')">닉</a></strong><p class="yg-ban-status-reason">사유</p><span>등록 26-08-31 12:00</span><span>29일 12시간 남음</span></article></div>"""
        row=u.parse_bans(BeautifulSoup(html,'html.parser'),'test',datetime(2026,9,1,tzinfo=u.KST))[0]
        self.assertEqual(row['release_at'],'2026-09-30T12:00:00+09:00')
    def test_bad_page_fails(self):
        with self.assertRaises(ValueError):u.parse_bans(BeautifulSoup('<html>error</html>','html.parser'),'test',datetime.now(u.KST))
    def test_incremental_stops_at_checkpoint_and_retains_authors(self):
        old=u.fetch;calls=[]
        html="""<table class="bd_list"><tr><td class="tit"><a href="/board/pan_prison/102">new</a></td><td class="name"><a onclick="YG_COMMON.show_nick_dropdown(this, '0', '8', 'N', 'N')">new name</a></td></tr><tr><td class="tit"><a href="/board/pan_prison/100">old</a></td></tr></table>"""
        def fake(url):calls.append(url);return BeautifulSoup(html,'html.parser')
        u.fetch=fake
        try:
            authors={'7':dict(member_id='7',nickname='old')}
            high,pages=u.collect_new(authors,100)
            self.assertEqual((high,pages),(102,1));self.assertEqual(set(authors),{'7','8'});self.assertEqual(len(calls),1)
        finally:u.fetch=old
if __name__=='__main__':unittest.main()
