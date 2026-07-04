# 공공데이터포털·지자체 채용 관련 오픈API 정리

> 수집일: 2026-07-04

공무원/공공기관 채용 도메인에서 프로그래밍으로 얻을 수 있는 데이터 소스를 정리한다.
※ data.go.kr, alio 등 일부 사이트는 본 세션 프록시에서 직접 접근이 차단(403)되어, 상세 명세는 검색 결과 기반. 실제 개발 시 각 페이지에서 Swagger/기술문서 확인 필요.

## 1. 지방자치단체 인터넷원서접수센터 (local.gosi.go.kr)

- 운영: 행정안전부/한국지역정보개발원(KLID). 2022년부터 17개 시·도별로 따로 운영되던 원서접수 사이트를 통합.
- **공식 오픈API는 제공하지 않음** (웹 페이지 조회만 가능) → 크롤링/수기 수집 대상.
- 얻을 수 있는 데이터(비로그인 조회 가능):
  | 메뉴 | URL | 내용 |
  |---|---|---|
  | 시도별 접수 | https://local.gosi.go.kr/klid/sido/examsido.do?strType=1 | 17개 시·도 진행 중 시험 목록 |
  | 시험공고 | 각 시도 페이지(예: 부산 gubun=11, 대구 gubun=12) | 임용시험 계획·필기합격자·면접시행계획 공고 |
  | 시험문제 및 정답 | https://local.gosi.go.kr/klid/sihum/exampaper.do | 지방직 필기 기출문제·정답 파일 |
  | 합격 및 면접 리스트 | https://local.gosi.go.kr/klid/sihum/exampass.do | 시도별 합격자 발표·면접 일정 |
- 활용: 지역별 면접 일정 캘린더 자동화, 공고문 PDF 수집(면접 방식·평정요소 추출).

## 2. 공공기관 채용정보 API (ALIO / JOB-ALIO)

- 배경: 기획재정부 공공기관 경영정보 공개시스템(ALIO)의 수시공시 채용정보. 채용포털은 job.alio.go.kr (2024년~ 알리오플러스 alioplus.go.kr로 개편 흐름).
- **오픈API 제공처 2곳**:
  1. **알리오 오픈데이터**: https://opendata.alio.go.kr/recruit/list — 공공기관 채용정보 오픈API 데이터조회. Swagger UI로 웹 기반 명세 제공(Edge/Chrome/Safari/Whale). 공공기관 정보 API(https://opendata.alio.go.kr/public_inst/list), 청년 일자리 지원시설 API(https://opendata.alio.go.kr/facility/list)도 병행 제공. 알리오플러스 OpenAPI 안내: https://www.alioplus.go.kr/openapi/openAPI.do
  2. **공공데이터포털 경유**: 「기획재정부_공공기관 채용정보 조회서비스」 https://www.data.go.kr/data/15125273/openapi.do
- 제공 데이터 항목: 채용공고 제목, 접수기간, 채용직무·인원, 채용 전형 단계, 접수방법, 공고 첨부파일 메타데이터, 근무지, 고용형태(정규/무기계약/체험형인턴 등), 학력·경력 요건 등. 「공공기관의 운영에 관한 법률」상 370여 개 공공기관의 신규채용 공시가 원천.
- 이용 방법(공공데이터포털 공통): data.go.kr 로그인 → 데이터찾기(오픈API 탭) → 활용신청 → 서비스키 발급 → REST 호출(JSON/XML). 개발계정 기본 트래픽 후 운영계정 증량 신청 가능.
- 파일데이터 대안: 「기획재정부_공공기관 채용정보」 https://www.data.go.kr/data/15050508/fileData.do , 「공공기관 신규채용현황」 https://www.data.go.kr/data/3045609/fileData.do
- 활용: AI 면접 서비스에서 "채용공고 → 직무 기반 예상질문 생성" 파이프라인의 공고 원천.

## 3. 인사혁신처 사이버국가고시센터 (gosi.kr)

- 국가공무원 공채(5·7·9급, 외교관후보자 등) 원서접수·시험정보 포털. **별도 오픈API는 없음**(웹 자료실 제공).
- 제공 자료(비로그인 열람 가능한 것 위주):
  | 자료 | 위치 | 내용 |
  |---|---|---|
  | 선택형 시험문제·정답 공개 | 시험문제/정답 메뉴 | 국가직 필기 기출 PDF, 정답, 이의제기 결과 |
  | 면접시험 안내 | https://www.gosi.kr/front/intv/intvPreview.do | 면접 절차, 평정요소, 준비 안내(경험·상황면접 과제 등) |
  | 시험통계/자료실 | 통계 메뉴 | 경쟁률, 합격선, 응시현황 통계 |
  | 연도별 시험계획 공고문 | 자료실 | 국가공무원 채용시험 일정·계획 원문 |
  | 시험절차 안내 | https://gosi.kr/cmm/inf/gosiExamProcess01.do | 단계별 절차(면접 포함) |
- 공공데이터포털에 올라온 인사혁신처 관련 데이터:
  - 「인사혁신처_국가공무원 시험일정」(파일) https://www.data.go.kr/data/3033611/fileData.do — 시험명, 선발예정인원, 원서접수기간, 시험단계, 시험일, 합격자발표일
  - 「인사혁신처_국가공무원 공개경쟁채용시험 모집직렬」(파일) https://www.data.go.kr/data/15129225/fileData.do
  - 「인사혁신처_사이버국가고시센터 국가공무원 채용시험 종합안내(FAQ)」(파일) https://www.data.go.kr/data/15120427/fileData.do — 시험 절차·종류·문의처 FAQ 텍스트(챗봇 학습에 유용)
  - 「인사혁신처_공공취업정보 조회」(오픈API) https://www.data.go.kr/data/15000485/openapi.do
  - 「인사혁신처_공공채용정보」(파일) https://www.data.go.kr/data/15151560/fileData.do
- 참고: 공공데이터포털은 3단계 이상 오픈포맷 파일데이터를 REST API(JSON/XML)로 자동변환 제공하므로, 위 파일데이터도 API처럼 호출 가능. 파일 다운로드는 로그인 불필요.

## 4. 기타 관련 소스

- **한국산업인력공단 오픈API**: https://openapi.hrdkorea.or.kr/main — 국가기술자격 정보, 과정평가형 자격, 일학습병행 등(면접 서비스의 자격증 검증·직무 매핑에 활용 가능).
- **워크넷/고용24 오픈API**(고용노동부): 민간·공공 구인구직 정보 — 직무 기술 키워드 확보용.
- **지자체별 인구·통계**: 「대구광역시_주민등록인구및세대현황」 https://www.data.go.kr/data/3077757/fileData.do , 부산 Big-데이터웨이브 https://data.busan.go.kr — 면접 답변용 지역 통계 근거.
- 주의: 국가법령정보(법제처 open.law.go.kr) API는 공직 관련 법령(지방공무원법, 공무원임용시험령 등) 조회에 활용 가능.

## 5. 종합: 데이터 획득 전략
1. **시험 일정·공고**: local.gosi.go.kr(지방직) 크롤링 + 인사혁신처 시험일정 파일데이터(국가직).
2. **면접 방식·평정요소**: 각 시·도 면접시험 시행계획 공고 PDF(local.gosi / 시청 홈페이지) 파싱.
3. **채용공고 텍스트**: ALIO 오픈API(공공기관) — 유일하게 완전한 REST API 제공.
4. **기출 필기문제**: gosi.kr·local.gosi.go.kr 공식 공개 PDF(저작권: 공공저작물, 출처표시 필요).
5. **면접 복원 질문**: 공식 API 없음 → 커뮤니티/학원 자료(00-sources.md 참고, 저작권 유의).

## 출처
- https://local.gosi.go.kr/ (지방자치단체 인터넷원서접수센터)
- https://local.gosi.go.kr/klid/sido/examsido.do?strType=1 (시도별 접수)
- https://local.gosi.go.kr/klid/sihum/exampaper.do (시험문제·정답)
- https://local.gosi.go.kr/klid/sihum/exampass.do (합격·면접 리스트)
- https://www.mpm.go.kr/mpm/info/fair/recruit/localgovt/localgovt01/localgovt01_01/ (인사혁신처: 지자체 채용제도)
- https://opendata.alio.go.kr/recruit/list (공공기관 채용정보 오픈API)
- https://opendata.alio.go.kr/public_inst/list (공공기관 정보 오픈API)
- https://opendata.alio.go.kr/facility/list (청년 일자리 지원 서비스)
- https://www.alioplus.go.kr/openapi/openAPI.do (알리오플러스 OpenAPI)
- https://job.alio.go.kr/ (JOB-ALIO)
- https://www.data.go.kr/data/15125273/openapi.do (공공기관 채용정보 조회서비스 API)
- https://www.data.go.kr/data/15050508/fileData.do (공공기관 채용정보 파일)
- https://www.data.go.kr/data/3045609/fileData.do (공공기관 신규채용현황)
- https://gosi.kr/ (사이버국가고시센터)
- https://www.gosi.kr/front/intv/intvPreview.do (면접시험 안내)
- https://gosi.kr/cmm/inf/gosiExamProcess01.do (시험절차 안내)
- https://www.data.go.kr/data/3033611/fileData.do (국가공무원 시험일정)
- https://www.data.go.kr/data/15129225/fileData.do (공개경쟁채용시험 모집직렬)
- https://www.data.go.kr/data/15120427/fileData.do (채용시험 종합안내 FAQ)
- https://www.data.go.kr/data/15000485/openapi.do (공공취업정보 조회)
- https://www.data.go.kr/data/15151560/fileData.do (공공채용정보)
- https://openapi.hrdkorea.or.kr/main (한국산업인력공단 오픈API)
- https://www.data.go.kr/data/3077757/fileData.do (대구시 주민등록인구)
- https://data.busan.go.kr/bdip/statistics/bStat.do (부산 Big-데이터웨이브)
