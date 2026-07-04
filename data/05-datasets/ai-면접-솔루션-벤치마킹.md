# AI 면접 솔루션 벤치마킹 — 국내 서비스 분석

> 수집일: 2026-07-04

우리 시스템(공무원 면접 AI, 지자체별·직렬별 특화)을 설계하기 위해 국내 AI 면접/면접 준비 서비스를 조사·비교한 문서.
웹 검색 기반이며, 가격·세부 스펙은 서비스 정책 변경이 잦으므로 구현 시점에 공식 페이지 재확인 필요.

---

## 1. 채용사(B2B) 측 AI 면접 솔루션

### 1.1 마이다스인(마이다스아이티) — inAIR / AI역량검사 / 잡다(JOBDA)
- 국내 AI 채용 시장의 사실상 표준. 2018년부터 신경과학 기반 "성과역량 예측" AI역량검사를 보급.
- 구성(대기업 채용에서의 일반 흐름):
  - **1단계**: 역량 게임 + 인성검사 (문자 추론, 도형 패턴, 반응속도 게임, 인성 설문)
  - **2단계**: 비동기 AI 비디오 면접 — 화면 질문에 제한 시간 내 녹화 제출, AI가 **표정·목소리·답변 내용** 분석
- 구직자 대상 무료 연습 채널: 잡다(jobda.im)의 역량검사 응시/튜토리얼(jobda.acca.ai/tutorial). 서울시 등 지자체가 마이다스 솔루션 기반 체험 프로그램 운영(seoulyouth.co.kr).
- B2B 확장: 잡다 컨시어지(채용 브랜딩·홍보·서류평가 자동화·인재상 커스터마이징 4종), JOBDA CC(대학 제휴), 잡플렉스(공채 ATS).
- 가격: B2B 계약형(비공개). 구직자용 연습은 무료(잡다 회원) 또는 대학/지자체 제휴 쿠폰.
- 시사점: "게임+영상+인성" 풀패키지형. 공무원 면접(구조화 개별면접)과는 포맷이 다름 → 직접 경쟁자라기보다 UX 벤치마크.

### 1.2 제네시스랩 — 뷰인터HR (B2B) / 뷰인터 (B2C)
- **뷰인터HR**: AI 영상면접 솔루션. 대기업·공공기관 등 **국내 250여 개 고객사**.
  - 기술: 전문 면접관 그룹이 수만 건의 면접 영상을 직접 평가한 결과를 알고리즘에 학습. 비언어적 요소 + **행동사건면접(BEI) 기반 30여 가지 세부 지표**로 평가.
  - 멀티모달(영상/음성/텍스트)로 신뢰감, 자연스러움, 침착성, 눈맞춤 등 커뮤니케이션 역량 평가. 미세 표정 변화까지 분석.
  - **GS인증 1등급** 획득 → 공공기관 우선구매 대상 자격. 공공 도입 실적: 강원랜드, 한국남동발전, LH, 육군/해군/해병대 간부·장교 선발, 한국자산관리공사, 병무청 모집병 면접 연구 등 (2020~2021부터).
  - 최근에는 채용을 넘어 임직원 역량평가로 확장(2025).
- **뷰인터(viewinter.ai)**: B2C 연습 앱(iOS/Android/웹). 표정·시선·언어·음성 동시 분석, Big5 성격특성 + 소셜스킬 10개 항목 리포트, AI 면접위원 평가·합격 가능성 점수·녹화 다시보기. 모의면접 1회 약 30~50분 소요.
  - 파생 상품: **뷰인터 생기부**(2024, 대입 생기부 기반 면접 연습), **AI 면접관 에이전트**(agent.viewinter.ai).
  - 가격: 이용권 구매형. 대학·기관 제휴 쿠폰(예: AI면접 20회 이용권) 배포가 활발 → 정확한 정가는 공식 사이트 확인 필요.
- 시사점: 공공기관 채용에 실제로 들어간 유일급 국내 솔루션. "전문 면접관 라벨링 → 평가모델 학습" 접근과 GS인증 전략은 공공 시장 진입 시 참고 가치가 큼.

## 2. 취업 플랫폼(B2C) 측 AI 면접 코칭

### 2.1 사람인 — 아이엠그라운드 / 더 레디 / AI 모의면접
- **아이엠그라운드**(AI 모의면접 앱) → **아이엠그라운드 더 레디**(커리어 관리 앱)로 확장.
- AI 면접 코칭: 모의면접 영상 촬영 → AI가 **표정, 목소리, 발음, 속도, 시선, 언어적 분석, 표절률 등 8가지 요소** 분석 → 리포트(면접 스타일 평가 + 개선 방향 + 실전 팁).
- 게임형 인적성검사(패턴 기억, 같은 그림 찾기 등) 포함. 대학 제휴 서비스 운영.
- **사람인 AI 모의면접**(m.saramin.co.kr/member/ai-interview): 이력서를 분석해 맞춤형 질문 생성, **답변에 따라 달라지는 대화형 꼬리질문** 제공. AI휴먼(가상 면접관)이 진행. 구매일로부터 30일 이용 등 이용권 방식.
- 기술 참고: 사람인 기술블로그(Medium saraminlab)에 "자기소개서 기반 개인화 면접 코칭"(LLM 활용) 아키텍처 공개. 챗GPT 기반 면접 기능에 대해 "가치·직무 질의에 한계" 지적 기사도 존재(매일일보) → LLM 단독 질문 생성의 품질 한계 사례.
- 시사점: "문서(자소서/이력서) → 개인화 질문 → 꼬리질문" 파이프라인이 우리 시스템과 가장 유사한 구조.

### 2.2 잡코리아 — AI 면접 연습 (영상분석+코칭)
- 기능: 직무·조직 적합 질문 자동 생성, 답변 내용 + **표정·음성 톤·태도 등 비언어 신호**를 데이터로 분석. 특이점은 **AI 분석 + 면접 전문가의 1~2일 내 사람 피드백** 하이브리드.
- 부가: AI면접 대비 온라인 강의(필수/상황제시형/개인맞춤형 질문 전략, 게임면접 고득점 전략).
- 주의: 모바일 공지에 "AI면접 서비스 종료" 사전공지가 있음 — 서비스 개편/축소 이력. 잡코리아는 2026년 사명을 '웍스피어(Worxphere)'로 바꾸고 AI 커리어 플랫폼("이력서 → AI 프로필")으로 전환 중.
- 시사점: 대형 플랫폼도 AI 면접 B2C 단독 상품은 유지가 어려웠음 → 수익모델 설계 시 참고(강의·컨설팅 결합 or B2G/B2B 제휴).

### 2.3 기타 B2C 서비스
- **하이잡(haijob.co.kr)**: 자소서 업로드 → 질문·답변 자동 생성, 실무/임원 등 유형별 연습 앱.
- **면접톡(interviewtalk.kr)**: 무료 AI 모의면접. 취업·대입·AI역량검사까지 커버하는 시뮬레이터.
- **에듀스(educe.co.kr)**: AI 취업플랫폼 내 AI면접 콘텐츠.
- **AceRound** 등 "실시간 면접 도우미" 계열: 무료 체험 + 월 23만 원, 프리미엄 세션 회당 2만~30만 원 수준의 가격대 보고됨(블로그 기준).
- **면접왕(interviewking.kr)**: 이름과 달리 '면접왕 이형'과 무관한 **AI 대입 모의면접** 서비스.

## 3. 사람 중심 면접 교육(비AI, 경쟁 대체재)

### 3.1 면접왕 이형 (유튜브 기반 취업 교육)
- 대기업 CHO 출신이 질문 의도·면접관 기대 답변을 강의. 유튜브 무료 콘텐츠 + Udemy 유료 강의.
- 유료 프로그램 '체인지업': 1개월 캠프 8.9만 원, 강의보다 스터디 자율 운영 방식. '자소서메이트' 등 자체 AI 도구도 병행.
- 시사점: 콘텐츠(질문 의도 해설)의 힘으로 커뮤니티/캠프를 파는 모델. AI 제품에 "왜 이 질문이 나오는가" 해설 레이어를 붙이는 아이디어의 원형.

### 3.2 공무원 면접 학원(스피치 학원)
- 이루다스피치(공무원 전용 트랙), 키움스피치, 원더공무원면접(노량진, 1:1 밀착코칭), DT당톡(1:1 코칭 + 모의면접 영상 피드백), 넥스트공무원(메가공무원 계열 면접 일정반) 등.
- 형태: 1:1 컨설팅, 조별 모의면접, 스피치 교정. 가격 비공개가 많고 회당 수만~수십만 원대 컨설팅 구조(블라인드 등 커뮤니티에서 비용 대비 효과 논쟁 활발).
- **AI를 전면에 내세운 공무원 면접 상품은 아직 학원가에 사실상 없음** — 대부분 사람 코치 중심. (검색 범위 내에서 "공무원 직렬·지자체 특화 AI 모의면접" 전문 서비스는 확인되지 않음.)

## 4. 공무원 특화 AI 면접 서비스 존재 여부 (핵심 질문)

- 결론: **"공무원 면접 특화 + AI" 전용 서비스는 아직 공백 시장에 가깝다.**
  - 대형 AI 면접 서비스(잡다, 뷰인터, 사람인, 잡코리아)는 모두 **민간기업 채용(AI역량검사/영상면접) 대비**가 중심. 공무원 구조화 면접(경험형·상황형·5분발표) 포맷을 지원하지 않음.
  - 공무원 학원가(에듀윌, 공단기, 메가공무원 등)는 면접 강의·모의면접반은 있으나 **사람 코치 기반**이며, AI 모의면접은 마케팅 수준 이상으로 확인되지 않음.
  - 면접톡·사람인 AI 모의면접이 "공공기관/공무원 면접"을 일부 카테고리로 흡수하고 있으나 범용 질문 수준.
  - 지자체·공공 무료 서비스: 서울시 AI 역량검사 체험(연 1만 명, 월 10회, 기업 기출 1만 개 제공, 서울시청년일자리센터 'AI면접체험실'), 강원일자리정보망 AI모의면접, 성남시일자리센터 등 — 다만 이는 **민간기업 취업용 AI역량검사 체험**이지 공무원 면접 대비가 아님. 관광공사 등 부처 행사에서도 AI영상면접 연습 부스 운영.

## 5. 기능 비교 요약

| 서비스 | 대상 | 질문 생성 | 답변 분석 | 표정/음성 분석 | 피드백 | 가격 모델 |
|---|---|---|---|---|---|---|
| 마이다스인 inAIR/잡다 | B2B(채용) + B2C(연습) | 고정+맞춤 | O (게임+영상) | O | 역량 리포트 | B2B 계약 / 연습 무료 |
| 뷰인터HR / 뷰인터 | B2B + B2C | 유형별 | O (BEI 30개 지표) | O (멀티모달, 미세표정) | Big5·소셜스킬 리포트, 합격가능성 점수 | B2B 계약 / B2C 이용권·제휴쿠폰 |
| 사람인 아이엠그라운드·AI모의면접 | B2C | 이력서 기반 개인화 + 꼬리질문 | O (8개 요소, 표절률 포함) | O | 리포트+개선방향 | 앱 무료 기능 + 이용권(30일) |
| 잡코리아 AI 면접 연습 | B2C | 직무·조직 기반 | O | O | AI + 전문가(1~2일) | 유료(강의 결합), 일부 종료 |
| 면접왕 이형 | B2C 교육 | - (강의) | 사람 | - | 사람 코칭 | 강의/캠프 8.9만 원~ |
| 공무원 스피치 학원 | B2C 공시생 | 사람 | 사람 | X | 1:1 코칭 | 회당 수만~수십만 원 |
| 지자체 무료 체험(서울 등) | B2C 청년 | 고정 | O | O | 결과 분석지+컨설팅 | 무료(세금) |

## 6. 우리 시스템의 차별화 포인트 제안

1. **지자체별 특화 (최대 차별점)**
   - 지방직 면접은 "해당 지자체 현안·역점 시책을 모르면 미흡" 구조인데, 기존 어떤 AI 서비스도 지자체별 질문 뱅크가 없음.
   - 지자체 공식 시책·인구소멸 대응·지역 축제/예산 이슈를 크롤링해 **시·도별 질문 자동 생성** → "부산시 9급 일반행정" 단위의 맞춤 모의면접 제공.
2. **직렬별 특화**
   - 일반행정/세무/사회복지/기술직/교육행정(교육청) 등 직렬별 전공·실무 질문 세트. 예: 교육행정직 단골 질문, 사회복지직 사례형 질문.
3. **공무원 면접 포맷 그대로 재현**
   - 국가직: 경험형·상황형 과제 20분 작성(각 12줄) → 5분발표 → 후속질문 흐름을 시뮬레이션. 지방직: 지자체별 사전조사서/발표면접 유형 반영.
   - 4대 평정요소(소통·공감/헌신·열정/창의·혁신/윤리·책임) 기준 채점 리포트 — 민간 서비스의 Big5·BEI 지표와 달리 **실제 평정표 언어**로 피드백.
4. **꼬리질문 대화형 엔진**: 사람인식 "답변에 따라 달라지는 꼬리질문"을 공직가치 검증 시나리오(상사의 부당한 지시, 민원 갈등, 규정 vs 재량)로 특화.
5. **AI-Hub 면접 데이터셋 활용**(동 폴더 ai-hub-면접데이터셋.md 참조): 음성·감정·의도 라벨 데이터로 한국어 면접 답변 분석 모델 보강.
6. **가격/유통 전략**: B2C 이용권 + 학원·인강사(에듀윌/공단기/메가공무원) B2B 제휴 + 지자체 일자리센터 B2G(서울시 사례처럼 무료 체험 예산 존재). 공공 납품 노리면 뷰인터HR처럼 GS인증 검토.
7. **리스크 참고**: 잡코리아 AI면접 종료 사례 → B2C 단독 과금은 취약. 챗GPT 단독 질문 생성 품질 한계 지적(사람인 기사) → 기출·평정요소 기반 RAG/검증 레이어 필요.

---

## 출처

- https://www.jobda.im/acca/test
- https://jobda.acca.ai/tutorial
- https://www.aceround.app/ko/blog/ai-interview-helper-korea/
- https://ncs.inha.ac.kr/bbs/ncs/3981/151014/artclView.do
- https://www.jobflex.com/ai/faq
- https://www.sedaily.com/NewsView/29XB502YLE
- https://seoulyouth.co.kr/
- https://www.dailysecu.com/news/articleView.html?idxno=151330
- https://viewinter.ai/
- https://viewinterhr.com/skills/
- https://agent.viewinter.ai/
- https://community.linkareer.com/employment_data/4980956
- https://www.moket.kr/tools/viewinter
- https://play.google.com/store/apps/details?id=ai.genesislab.viewinter
- https://apps.apple.com/kr/app/viewinter/id1434802044
- https://www.kma.or.kr/kr/usrs/eduRegMgnt/eduRegMgntForm.do?mkey=9&cateNm=spcInterview
- https://www.hankookilbo.com/News/Read/A2025112609440000991
- https://zdnet.co.kr/view/?no=20230914181042
- https://zdnet.co.kr/view/?no=20230727121027
- https://www.venturesquare.net/906997
- https://m.ddaily.co.kr/page/view/2024112610074693105
- https://www.sedaily.com/article/13456167
- https://www.saramin.co.kr/zf_user/help/live/view?idx=108749&listType=news
- https://www.saramin.co.kr/zf_user/help/live/view?idx=101366&listType=news
- https://www.saramin.co.kr/zf_user/help/live/view?idx=104379&listType=news
- https://www.saramin.co.kr/zf_user/help/live/view?idx=106382&listType=notice
- https://m.saramin.co.kr/events/iam-ground-app/app-intro
- https://m.saramin.co.kr/member/ai-interview
- https://medium.com/saraminlab/ai-면접-코칭-자기소개서-기반-개인화-면접-코칭-서비스-203a7e75d8a4
- https://www.m-i.kr/news/articleView.html?idxno=1004551
- https://www.jobkorea.co.kr/starter/ai/analysis
- https://m.jobkorea.co.kr/AI/Analysis
- https://news.nate.com/view/20260129n37183
- https://v.daum.net/v/20260215094126672 (AI 모의면접·자소서 코칭 확산 기사, 본문 접근 403)
- https://www.udemy.com/course/interviewclass/
- https://namu.wiki/w/면접왕%20이형
- https://community.linkareer.com/STEM_mentoring/3530120
- https://nextleveltransform.com/nlt_blog_page/hywmini
- https://interviewking.kr/
- https://www.haijob.co.kr/
- https://www.interviewtalk.kr/
- https://www.educe.co.kr/aicontents/interview
- https://www.elooda.co.kr/civil/
- http://www.kiwoomspeech.com/
- https://wonderinterview.co.kr/
- https://dangtalk.co.kr/면접학원-비용과-후기/
- https://www.teamblind.com/kr/post/형들-면접학원-도움돼-HFOTACkK
- https://gongssel.megagong.net/c/gongssel/schedule/2025/interview/index.asp
- https://mediahub.seoul.go.kr/archives/2014103
- https://youth.seoul.go.kr/content.do?key=2310100016
- https://opengov.seoul.go.kr/mediahub/22963225
- https://job.gwd.go.kr/gwjob/empymn_sprt/interview_ai
- https://academy.visitkorea.or.kr/fair/fairAIVideo.do
