# 스타감옥 죄수현황

스타대학 현재 밴 회원 중 스타감옥 작성 이력이 있는 회원을 표시. 스타감옥에서도 밴 상태인 회원은 제외. 수동 지정은 `data/manual-overrides.json`에서 별도 관리하며 화면에도 표시.

- 화면: 3열 기본. 모바일 2열.
- 배포: Vercel 정적 웹. `npm run build`는 공개 웹 파일만 dist에 복사.
- 데이터: GitHub `data` 브랜치. 앱 배포와 독립적으로 갱신.
- 이미지: `/status.jpg` 고정 URL. Vercel 외부 rewrite로 data 브랜치 이미지 제공.
- 자동 갱신: 매시간 17분 GitHub Actions 실행. 스케줄은 GitHub 상황에 따라 지연 가능.
- 수동 실행: Actions → Refresh prison roster → Run workflow.

## 갱신 순서

1. 마지막 성공한 작성자 목록·글 번호 불러오기. 최초는 seed 디렉터리 사용.
2. 스타감옥 최신 글부터 기존 확인 번호까지 조회. 공지는 종료 기준에서 제외.
3. 양쪽 게시판의 현재 밴 목록 전체 조회.
4. 회원번호 대조, 무기수 예외 적용, 등록일+기간으로 출소 예정일 계산.
5. Chromium이 1200px 너비·3열 페이지를 전체 캡처. 글꼴·이미지·데이터 로딩 완료 대기.
6. 데이터와 스크린샷 둘 다 성공한 경우에만 data 브랜치에 함께 커밋. 실패하면 기존 상태 유지.

`status.jpg`는 게시물을 다시 열 때 갱신된 이미지를 받는 방식. GitHub 원본 캐시 때문에 짧은 반영 지연 가능. 열린 이미지의 실시간 자동 교체는 아님.

## 로컬

`python -m http.server 4173 --bind 127.0.0.1`

`python -m unittest discover -s tests`

`python scripts/update.py --state-dir live` / `npm ci` / `npx playwright install chromium` / `npm run capture`

원본 삭제·비공개 글은 수집하지 못함. 이미 확인한 작성 이력은 유지. 회원번호 미노출 건은 보류. 무기수 수동 지정은 실제 원본 밴 정보와 별개.
