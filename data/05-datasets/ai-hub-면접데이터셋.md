# AI-Hub 채용면접 인터뷰 데이터셋 정리

> 수집일: 2026-07-04

## 1. 채용면접 인터뷰 데이터 (dataSetSn=71592)

- 페이지: https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71592
- 운영: 한국지능정보사회진흥원(NIA) AI-Hub / 과기정통부 '인공지능 학습용 데이터 구축사업' 산출물
- 구축년도: 2022년(사업연도 기준), 데이터 유형: **오디오 + 텍스트**
- ※ aihub.or.kr은 봇 차단(403)으로 본 세션에서 원문 직접 열람 불가 — 아래 내용은 검색 결과 스니펫 기반이며, 세부 수치는 페이지에서 재확인 권장.

### 1.1 개요
실제 채용면접과 유사한 환경에서 **질문·답변 음성을 제작**하고, 이를 **텍스트로 변환(전사)**한 뒤 답변의 **내용 요약, 감정(emotion), 의도(intent)를 라벨링**한 데이터셋. 원격(비대면) 면접 서비스 고도화, 채용면접 데이터의 언어적 분석을 목적으로 구축.

### 1.2 규모
| 구분 | 건수 |
|---|---|
| 원천 데이터(음성 등) | 168,268건 |
| 라벨링 데이터(JSON) | 84,134건 |

- 원천:라벨링이 2:1인 구조(질문+답변 음성 쌍 → 1개 라벨링 JSON으로 추정).
- 메타데이터에 직업군, 채널, 면접 장소, 성별, 나이대, 경력 여부 포함 → 직군별/연령별 분할 학습 가능.

### 1.3 라벨링 구조(JSON)
```
dataSet
├─ info                # 메타데이터: 작성일자, 직업군, 채널, 면접장소, 성별, 나이대, 경력여부
├─ question
│   ├─ raw             # 질문 텍스트, 어절 수
│   ├─ emotion         # 질문 감정 라벨
│   └─ intent          # 질문 의도 라벨
├─ answer
│   ├─ raw             # 답변 텍스트, 어절 수
│   ├─ emotion         # 감정: 텍스트 구간, 상세 감정, 상위 감정 카테고리
│   ├─ intent          # 의도: 텍스트 구간, 상세 의도, 상위 의도
│   └─ summary         # 답변 내용 요약
└─ rawDataInfo         # 음성 원천 정보: 파일형식, 크기, 길이, 샘플링비트, 채널수, 샘플링레이트, 저장위치
```

### 1.4 라이선스·이용조건 (AI-Hub 공통 이용정책)
- 회원가입 + 휴대폰 본인인증 후 데이터셋 페이지 [다운로드] 버튼 → 이용목적 기재 신청 → **자동 승인** 후 다운로드.
- **국내 이용 원칙**: 원본 데이터(json, wav 등)의 국내외 외부 유출 금지. (일부 데이터는 해외 이용 제한 명시 — 데이터별 안내 확인)
- **영리 활용**: AI-Hub 데이터로 학습한 **모델**의 영리적 판매·활용은 허용. 단 AI-Hub 데이터 사용 사실 명시 필요.
- **재배포 금지**: NIA·구축기업과 사전 협의 없이 데이터를 재가공하여 배포하는 행위는 원칙적 불가.
- 논문 게재 시 필수 문구: "이 연구는 과학기술정보통신부의 재원으로 한국지능정보사회진흥원의 지원을 받아 구축된 데이터를 활용하여 수행된 연구입니다. 본 연구에 활용된 데이터는 AI 허브(aihub.or.kr)에서 다운로드 받으실 수 있습니다."

### 1.5 다운로드 방법
1. aihub.or.kr 회원가입 → 휴대폰 인증
2. 데이터셋 페이지에서 [다운로드] 클릭 → 이용목적 입력(자동승인)
3. 웹 다운로드 또는 전용 다운로더(구 innorix / aihubshell CLI) 사용
   - `aihubshell` CLI: API 키 발급 후 `aihubshell -mode d -datasetkey 71592` 형태로 대용량 일괄 다운로드 가능 (참고: 데보션 기술블로그 "AI 허브에서 데이터를 간편하게 받아오기")

### 1.6 AI 면접 시스템에서의 활용 방안
- **면접 질문-답변 페어 학습**: question/answer raw 텍스트로 질문 생성 모델·모범답변 평가 모델 파인튜닝.
- **답변 요약**: answer.summary를 지도 데이터로 답변 자동 요약(면접관 대시보드용) 모델 학습.
- **감정·의도 분석**: emotion/intent 라벨로 답변의 긴장·자신감 등 감정 분류기, 답변 의도(경험 서술, 회피, 강점 어필 등) 분류기 학습 → 피드백 엔진.
- **STT 도메인 적응**: 면접 도메인 음성 168k건으로 Whisper 등 STT 모델의 면접 어휘 적응(직무 용어, 존댓말 구어체).
- **모의면접 대화 시뮬레이터**: 직업군 메타데이터로 직군별 면접관 페르소나 구성.
- 한계: **사기업 채용면접 중심**이므로 공무원 면접(공직가치·시정 질문)에는 도메인 갭 존재 → 공무원 면접 복원 기출로 보강 필요. 원본 재배포 금지이므로 서비스에는 '학습된 모델'만 탑재해야 함.

## 2. 그 외 면접·음성·감정 관련 AI-Hub 데이터셋

| 데이터셋 | dataSetSn | 내용·규모 | 활용 포인트 |
|---|---|---|---|
| 감성 대화 말뭉치 | 86 | 감정 라벨(우울 등 60가지) 텍스트 대화 코퍼스 | 감정 분류, 공감형 응답 |
| 감정 분류를 위한 대화 음성 데이터셋 | 263 | 7감정(happiness/angry/disgust/fear/neutral/sadness/surprise), 5인 교차 라벨, csv 메타 | 음성 감정 인식(SER) |
| 한국어 감정 정보가 포함된 연속적 대화 데이터셋 | 271 | 연속 대화 10,000세트 + 단발성 문장 55,627개, 7감정 태깅 | 대화 흐름 감정 추적 |
| 한국어 대화 데이터셋 | 272 | 일상 한국어 대화 | 대화 모델 기초 |
| 감정 음성합성 데이터셋 | 286 | 여성 성우 1인, 7감정 × 3,000발화 = 21,000파일 | 감정 TTS(면접관 음성) |
| 감정 음성 데이터셋 | 637 | 전문성우 8인 206시간 + 일반인 501인 127시간, 전사문+감정태깅 | SER 학습 |
| 감정이 태깅된 자유대화(성인) | 71631 | 성인 자유대화 음성, 감정 태깅 | 성인 화자 SER |
| 감정이 태깅된 자유대화(청소년) | 71632 | 청소년 3,000시간, 11개 주제, 7감정(기쁨/놀라움/두려움/사랑스러움/슬픔/화남/없음) | 연령별 SER |
| 멀티모달 영상 | (구)137 | 6,000클립·110시간17분, 감정·성별·연령·발화스크립트·대화의도·전략 라벨 | 표정+음성 멀티모달 면접 분석 |
| 한국인 감정인식을 위한 복합 영상 | (구)27716 | 표정·영상 기반 감정 인식 | 표정 분석 |
| 자유대화 음성(일반남녀) | - | 2,000명+ 화자, 약 4,000시간 | STT 기반 모델 |
| 자유대화 음성(노인남녀) | - | 1,000명+ 화자, 약 3,000시간 | 고연령 화자 STT |
| 진로문장완성검사 텍스트 데이터 | 71791 | 진로 상담 텍스트 | 진로·직무 적합성 분석 |
| 용도별 목적대화 데이터 | 544 | 목적지향 대화 | 태스크 지향 대화 모델 |

- 전체 목록 탐색: https://aihub.or.kr/aihubdata/data/list.do?searchKeyword=감정 (키워드 검색: 면접, 감정, 상담, 자유대화)
- AI-Hub 데이터셋 메타 목록은 공공데이터포털 파일데이터로도 제공: 「한국지능정보사회진흥원_AI허브 데이터셋 정보」 https://www.data.go.kr/data/15135578/fileData.do

## 출처
- https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71592 (채용면접 인터뷰 데이터)
- https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&dataSetSn=71592 (동일 페이지)
- https://www.aihub.or.kr/intrcn/guid/usagepolicy.do?currMenu=151&topMenu=105 (AI-Hub 이용정책)
- https://www.aihub.or.kr/useStplat.do?currMenu=110&topMenu=110 (이용약관)
- https://www.aihub.or.kr/aihubnews/faq/list.do (FAQ: 논문 명시 문구, 영리 활용, 유출 금지)
- https://aihub.or.kr/intrcn/guid/dataprcuse.do?currMenu=151&topMenu=105 (데이터 구축·활용 안내)
- https://devocean.sk.com/blog/techBoardDetail.do?ID=166594&boardType=techBlog (aihubshell 다운로드 방법)
- https://www.data.go.kr/data/15135578/fileData.do (AI허브 데이터셋 정보 파일데이터)
- https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&dataSetSn=86 (감성 대화 말뭉치)
- https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=263 (감정 분류 대화 음성)
- https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=271 (감정 연속 대화)
- https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=272 (한국어 대화)
- https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=286 (감정 음성합성)
- https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=637 (감정 음성)
- https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71631 (감정 태깅 자유대화 성인)
- https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&dataSetSn=71632 (감정 태깅 자유대화 청소년)
- https://aihub.or.kr/aidata/137 (멀티모달 영상)
- https://aihub.or.kr/aidata/27716 (한국인 감정인식 복합 영상)
- https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&aihubDataSe=data&dataSetSn=71791 (진로문장완성검사)
- https://www.gimi9.com/dataset/aihub_263/ (감정 대화 음성 미러 정보)
- https://ko.wikipedia.org/wiki/AI_Hub (AI-Hub 개요)
