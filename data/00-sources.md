# 공무원 면접 자료 소스 총정리

> 수집일: 2026-07-04

공무원 면접 대비 서비스/데이터 구축에 쓸 수 있는 자료 소스를 신뢰도·저작권 관점에서 정리.

## 1. 공식 소스 (정부·지자체) — 신뢰도 ★★★★★

| 소스 | URL | 제공 자료 | 비고 |
|---|---|---|---|
| 사이버국가고시센터 | https://gosi.kr | 국가직 시험계획·필기 기출/정답·면접시험 안내·시험통계 | 국가직 면접 절차/평정요소의 1차 출처 |
| 지방자치단체 인터넷원서접수센터 | https://local.gosi.go.kr | 17개 시·도 시험공고, 필기 기출·정답, 합격/면접 일정 | 지방직 공고 통합 창구, API 없음 |
| 인사혁신처 | https://www.mpm.go.kr | 공무원 인사제도, 면접 평정요소 개정 사항, 공직박람회 자료 | 평정요소 변경(소통·공감/헌신·열정/창의·혁신/윤리·책임) 확인처 |
| 각 시·도 인사위원회(시청 홈페이지) | 예: busan.go.kr 시험공고, daegu.go.kr | 면접시험 시행계획 공고(면접 방식·일정·유의사항 원문) | 연도별 면접 형식 변화의 유일한 공식 근거 |
| 공공데이터포털 | https://www.data.go.kr | 시험일정·모집직렬·FAQ 파일데이터, 채용정보 API | 기계가독 데이터 |
| ALIO/JOB-ALIO | https://job.alio.go.kr , https://opendata.alio.go.kr | 공공기관 채용공고 오픈API | 공공기관(공기업) 채용 전용 |
| 정책브리핑 | https://www.korea.kr | 제도 변화 기사(예: "새로 생긴 공무원 면접 5분 스피치 해보니") | 공공누리 라이선스, 인용 용이 |
| 시정 공식 자료 | busan.go.kr(시정브리핑·예산), daegu.go.kr(주요정책) | 시정 비전·정책·예산 | 면접 시정질문 답변 근거의 표준 |

- **저작권**: 공고문·기출문제·정책자료는 대부분 공공저작물(공공누리 제1~4유형). 유형 확인 후 출처 표시하면 서비스 활용 가능. 단 문제 지문에 제3자 저작물(지문 인용)이 포함된 경우 주의.
- **신뢰도 특징**: 면접 '방식'은 완벽하게 확인 가능하나, 면접 '질문'(비공개)은 공식 소스에 없음 → 복원 자료는 아래 커뮤니티 의존.

## 2. 수험 커뮤니티·학원 사이트 — 신뢰도 ★★★☆☆ (교차검증 필요)

| 소스 | URL | 특징 |
|---|---|---|
| okpass(제일고시학원, 대구) | http://okpass.com / okpass.org → 복원게시판(restore_interview) | **시도별·연도별 면접 복원 질문 최다 보유**(부산 2021~2025, 대구 등). 대구 소재 학원이라 TK 자료 강함. 봇 차단 있음 |
| 공기출 | https://0gichul.com | 필기 기출·해설·본문검색 무료 제공, 일정/공고 게시판, 합격수기. 면접 자료는 부수적 |
| 독공사(독하게 공무원 준비하는 사람들) | 네이버 카페 (회원 약 80~93만) | 합격수기 4,400개+, 면접 후기, 데이터랩(합격선·경쟁률·TO). 로그인 필요 |
| 피티윤x해커스 '공직역량발전소' | https://cafe.daum.net/pt.yunssem | 면접 전문 카페. 지역별 면접 형식 팩트글(부산 3분발표 등), 사전조사서 양식(경기·충북·대구), 직렬별 도움자료 |
| 공무원 국어 이유진 카페 | https://cafe.daum.net/naraeyoujin → ★면접복기 게시판 | 연도·지역·직렬별 상세 면접 복기(2024 부산 일반행정 등) |
| 디시인사이드 공무원 갤러리들 | gall.dcinside.com (gongsistudy, gongsi, gisulzik 미니갤) | 생생한 당일 복기(2024 대구 일행 등). 익명성 → 검증 필수 |
| 더쿠/보배 등 일반 커뮤니티 | theqoo.net 등 | 산발적 면접 후기 |
| 학원 계열 | 에듀윌(govlab.eduwill.net), 공단기(gong.conects.com), 메가공무원(lab.megagong.net), 대방고시(daebanggosi.com), 당톡(dangtalk.co.kr) | 면접 가이드, 공고 PDF 미러, 직렬별 후기. 대방고시는 공고 PDF 아카이브 유용 |
| 법률저널/공무원저널 계열 언론 | lec.co.kr, gosiweek.com, psnews.co.kr | 면접 방식 해설 기사, 과거 기출 유형 보도 — 준공식 검증 소스 |

- **신뢰도 주의점**: 복원 질문은 기억 의존이라 표현이 부정확할 수 있고, 같은 지역이라도 조(면접관)별로 질문이 다름. 최소 2개 소스 교차확인 권장. 연도 미상 자료가 많아 태깅 시 '연도미상' 구분 필요.
- **저작권 주의**:
  - 학원 사이트(okpass 등)의 복원 정리물은 **학원의 편집저작물** — 무단 대량 복제·재게시 불가. 서비스에는 질문 '사실' 자체를 재구성(패러프레이즈)해 수록하고 출처 표기.
  - 카페·커뮤니티 게시글은 **작성자 개인 저작물** — 원문 전재 금지, 요약·통계화 수준으로 활용.
  - 크롤링 시 robots.txt·이용약관 확인(대부분 로그인 장벽 + 봇 차단 존재).

## 3. 블로그·유튜브 — 신뢰도 ★★☆☆☆~★★★☆☆

### 블로그
- 브런치 면접 후기·기출 모음(예: brunch.co.kr/@jinjoa1204/35 "자주 출제되는 기출질문 모음", brunch.co.kr/@ing-yeo/24 국가직 전산직 후기) — 개인 경험 기반, 구체적.
- 티스토리/개인 블로그 면접 전략글(예: mr2bbuni.com 지방직 9급 면접 후기·전략) — 광고성/재탕 글 혼재, 원출처 확인 필요.
- 네이버 블로그: "지역명 + 면접 복기" 검색 시 당해 연도 후기 다수. 학원 바이럴 글 주의.

### 유튜브
- 피티윤xHackers (https://www.youtube.com/@ptYUN) — 공무원 면접 1타 강사 채널, 지역별 면접 특징·모의면접.
- 공단기/에듀윌/메가공무원 공식 채널 — 면접 설명회 영상(연도별 형식 변화 확인에 유용).
- 면접왕 이형 — 사기업 면접 중심이나 답변 구조화 방법론 참고용(공무원 특화 아님).
- 지역 MBC/KBS 뉴스 채널 — 시정 현안 브리핑(면접 시사 소재, 예: 대구MBC 청년유출 보도).

- **저작권 주의**: 영상·블로그의 정리 콘텐츠(질문 리스트, 답변 예시)는 저작물. 서비스 데이터로 쓸 때는 사실 정보만 추출하고 표현은 자체 작성. 유튜브 스크립트 대량 추출은 약관 위반 소지.

## 4. 데이터셋·API (별도 문서 참조)
- AI-Hub 채용면접 인터뷰 데이터 등 → `05-datasets/ai-hub-면접데이터셋.md`
- 공공데이터포털·ALIO·gosi 계열 API → `05-datasets/공공데이터-API.md`

## 5. 소스 운용 원칙 (권장)
1. **면접 방식/일정/평정요소** = 공식 공고 원문만 사용 (매년 갱신 확인).
2. **복원 기출 질문** = 커뮤니티·학원 자료를 교차검증 후 자체 문구로 재작성, [연도/직렬/유형] 태깅, 출처 URL 보관.
3. **시정·정책 정보** = 시 공식 자료 + 지역 언론 2개 이상 교차. 선거(2026.6. 지방선거로 부산 전재수·대구 추경호 체제) 이후 정책 변경 여부 필수 재확인.
4. **저작권** = 원문 전재 금지, 사실 추출 + 출처 표시. 공공누리 자료 우선 사용.

## 출처
- https://gosi.kr/ 및 https://www.gosi.kr/front/intv/intvPreview.do
- https://local.gosi.go.kr/
- https://www.mpm.go.kr/mpm/info/fair/recruit/localgovt/localgovt01/localgovt01_01/
- https://www.busan.go.kr/depart/jobexam01/
- https://www.daegu.go.kr/eco/index.do?menu_id=00936470
- https://www.data.go.kr/
- https://job.alio.go.kr/ , https://opendata.alio.go.kr/recruit/list
- https://www.korea.kr/news/examPassView.do?newsId=148800765 (5분 스피치 체험기)
- http://okpass.com/work/problem_2_1.php , http://okpass.org/work/problem_1_1.php (okpass 기출·복원)
- https://0gichul.com/ (공기출)
- https://edu.dasfl.com/entry/독하게-공무원-준비하는-사람들-독공사-가이드 (독공사 가이드)
- https://m.ekn.kr/view.php?key=20231106001559239 (독공사 소개 기사)
- https://www.gosiweek.com/article/1065596756041943 (독공사 합격수기 기사)
- https://cafe.daum.net/pt.yunssem (피티윤 공직역량발전소)
- https://m.cafe.daum.net/naraeyoujin/dA0q (이유진 카페 면접복기 게시판)
- https://gall.dcinside.com/mini/board/view/?id=gongsistudy&no=285395 (디시 대구 면접 복기)
- https://theqoo.net/review/556437628 (더쿠 지방직 면접 후기)
- https://govlab.eduwill.net/exam/interview (에듀윌 면접 안내)
- https://gong.conects.com/exam_info/bbs/view_m/exam_info_strategy?document_idx=3004736 (공단기 면접 안내)
- https://dangtalk.co.kr/ (당톡 면접학원 후기 아카이브)
- https://brunch.co.kr/@jinjoa1204/35 (기출질문 모음 브런치)
- https://brunch.co.kr/@ing-yeo/24 (전산직 면접 후기)
- https://mr2bbuni.com/entry/📘-2025-지방직-9급-면접-후기-및-준비-전략-–-실전-질문부터-발표형-대비까지
- https://www.youtube.com/@ptYUN (피티윤xHackers)
- https://namu.wiki/w/면접왕%20이형 (면접왕 이형)
- https://namu.wiki/w/공무원%20시험/면접 (나무위키 면접 개요)
- http://www.lec.co.kr/news/articleView.html?idxno=22240 (법률저널 사전조사서)
- https://www.psnews.co.kr/news/articleView.html?idxno=1454281 (퍼블릭뉴스 대구 면접 기사)
