# 질문 선택 엔진 프로토타입 (question_selector.py)

공무원 AI 모의면접 MVP의 **질문 출제(선택) 엔진** 프로토타입.
설계 문서(`data/06-answer-guides/모의면접-세션-설계.md` §3, `data/08-system/아키텍처-종합설계.md` §4-1)의
질문 선택 알고리즘을 **Python 표준 라이브러리만으로** 실행 가능하게 구현했다.
외부 의존성 없음. 동일 seed면 결과가 항상 동일(결정적).

---

## 1. 사용법

```bash
# 기본 (지방직 표준 트랙, 실전 모드, seed=42)
python3 question_selector.py --region 서울특별시 --job 일반행정직

# 트랙/난이도/시드 지정
python3 question_selector.py --region 부산광역시 --job 사회복지직 --track 지방직표준 --difficulty 초급 --seed 7

# 국가직 9급형 (지역현안 제외, 상황형 강화)
python3 question_selector.py --region 서울특별시 --job 일반행정직 --track 국가직9급

# JSON 출력 (파이프라인 연동용)
python3 question_selector.py --region 경기도 --job 전산직 --json
```

옵션:

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--region` | (필수) | 지자체명. 예: `서울특별시`, `부산광역시`, `경기도` |
| `--job` | (필수) | 직렬명. 예: `일반행정직`, `사회복지직`, `전산직` |
| `--track` | `지방직표준` | `지방직표준` \| `국가직9급` |
| `--difficulty` | `실전` | `실전` \| `초급`(고신뢰 라벨 우선) |
| `--seed` | `42` | 랜덤 시드(가중 샘플링 재현) |
| `--questions` | repo 기본 경로 | `questions.json` 경로 |
| `--json` | off | 결과를 JSON으로 출력 |

프로그램 임포트도 가능:

```python
import question_selector as qs
questions = qs.load_questions()
result = qs.select_questions("경기도", "전산직", track="지방직표준",
                             difficulty="실전", seed=42, questions=questions,
                             recent_ids={"q00519"})  # 최근 3세션 출제분(재출제 억제)
print(qs.format_result(result))
```

`select_questions(region, job, track='지방직표준', difficulty='실전', n_by_type=None, ...)`
— `n_by_type`로 유형별 쿼터를 직접 지정 가능(예: `{'공직가치':2,'인성':2,'직무':3,'지역현안':2,'상황형':1}`).

---

## 2. 알고리즘

### 2-1. 유형 쿼터 (설계 §3-2)

지방직 표준형 기본 쿼터: **공직가치 2 + 인성 2 + 직무 3 + 지역현안 2 + 상황형 1 = 10**

트랙/지역별 조정(코드 `QUOTA_TRACKS`, `QUOTA_REGION_OVERRIDE`):

| 트랙/지역 | 공직가치 | 인성 | 직무 | 지역현안 | 상황형 |
|---|---|---|---|---|---|
| 지방직표준(기본) | 2 | 2 | 3 | 2 | 1 |
| 국가직9급 | 2 | 2 | 3 | 0 | 3 |
| 서울특별시 | 2 | 3 | 3 | 1 | 1 |
| 대구광역시 | 2 | 1 | 3 | 3 | 1 |
| 인천광역시 | 2 | 2 | 2 | 2 | 1 |

### 2-2. 후보 필터링 — 완화 단계 (설계 §3-1, 아키텍처 §4-1)

**핵심 설계**: 지역×직렬 동시 태깅은 전체의 3.4%(106건)로 극히 희소하다(데이터셋 리포트 §5-3).
따라서 단일 교차 매칭에 의존하지 않고 **"지역 축(지역현안) + 직렬 축(직무)을 각각 뽑아 조합"** 한다.

유형별 쿼터를 채울 때 **좁은 조건부터 시도하고, 부족하면 단계적으로 넓힌다**:

1. **1순위 (지역+직렬)**: `region==선택 AND job==선택`
2. **2순위 (축 분리)**: `(region==선택 AND job==null)` + `(job==선택 AND region==null)`
3. **3순위 (공통)**: `category==common`

- 국가직 트랙은 `region != null` 항목을 전량 제외한다.
- 각 유형은 1순위에서 쿼터를 못 채우면 2순위 후보를 더하고, 그래도 부족하면 3순위(공통)까지 확장한다.
- 최종적으로도 부족하면 `shortfall`로 표시 → 실제 시스템에서는 **LLM 생성 질문으로 보충**(`generated:true`, 피드백에 "예상 질문" 표기).

### 2-3. 가중치 (설계 §3-2)

쿼터 내 개별 선택은 가중 비복원 샘플링(Efraimidis–Spirakis, seed 고정):

```
w = w_reliability × w_year × w_novelty
```

- `w_reliability`: 확인 1.0 / 기출 0.9 / 복원 0.8 / 빈출 0.7 / 예상 0.5 / null 0.4
- `w_year`: 2024+ → 1.2 / 2020–2023 → 1.0 / 그 이전 → 0.7 / null → 0.9
- `w_novelty`: 최근 3세션 출제분(`recent_ids`) → 0.1 (재출제 억제), 그 외 1.0

`difficulty=초급`이면 각 유형에서 고신뢰 라벨(확인·복원·기출·빈출)을 **우선** 사용하고, 부족할 때만 전체 풀로 폴백한다.

### 2-4. 중복 제거 (설계 §3-1 [2])

설계 원안은 임베딩 유사도 ≥0.9 근접쌍 제거지만, 표준 라이브러리만 쓰므로
**정규화 텍스트(NFKC·공백 제거·소문자) 완전일치 기준**으로 근사 중복 제거하고, 충돌 시 `reliability`가 높은 쪽을 유지한다.

### 2-5. 출제 순서 배치 (설계 §3-3)

고정 골격: **오프닝(인성 자기소개류) → 공직가치 → 직무 → 지역현안 → 상황형 → 마무리(WRAPUP)**

배치 규칙:
- 오프닝은 인성 1문(자기소개/평판류)을 맨 앞에.
- **동일 유형 3연속 금지**.
- **상황형은 세션 중반 이후**에 배치(긴장도 곡선 관리).
- 마무리(WRAPUP, "마지막으로 하고 싶은 말")는 질문 큐 외 고정 멘트로 맨 끝에 표시.

---

## 3. 실행 예시 출력

```
$ python3 question_selector.py --region 경기도 --job 전산직
========================================================================
 모의면접 질문 세트  |  경기도 · 전산직 · 트랙=지방직표준 · 난이도=실전 · seed=42
========================================================================
쿼터: 공직가치2  인성2  직무3  지역현안2  상황형1  (합계 10)
------------------------------------------------------------------------
 1. [오프닝  ] 자기소개와 지원동기를 말해보라
      └ id=q00519 type=인성 region=경기도 job=None 신뢰도=무라벨 연도=미상 매칭=축분리
 2. [공직가치 ] 청렴이 왜 중요한가? 청렴을 실천할 방안은?
      └ id=q00518 type=공직가치 region=경기도 job=None 신뢰도=무라벨 연도=미상 매칭=축분리
 3. [공직가치 ] 공무원으로서 가장 중요한 덕목은 무엇인가?
      └ id=q00516 type=공직가치 region=경기도 job=None 신뢰도=무라벨 연도=2022 매칭=축분리
 4. [직무   ] 데이터기반행정 활성화에 관한 법률에 대해 아는가?
      └ id=q03000 type=직무 region=None job=전산직 신뢰도=무라벨 연도=미상 매칭=축분리
 5. [직무   ] 공공부문 클라우드 전환(클라우드 네이티브) 정책에 대해 아는가? G-클라우드란?
      └ id=q02972 type=직무 region=None job=전산직 신뢰도=무라벨 연도=미상 매칭=축분리
 6. [지역현안 ] 경기도(우리 시) 시책 중 아는 것을 말해보라 / 관심 있는 정책은?
      └ id=q00526 type=지역현안 region=경기도 job=None 신뢰도=무라벨 연도=미상 매칭=축분리
 7. [직무   ] 디지털 격차(정보 소외계층) 해소를 위한 방안을 제시해보라.
      └ id=q03011 type=직무 region=None job=전산직 신뢰도=빈출 연도=미상 매칭=축분리
 8. [지역현안 ] 우리 시(군)의 현재 문제점은 무엇이라고 생각하는가?
      └ id=q00527 type=지역현안 region=경기도 job=None 신뢰도=무라벨 연도=미상 매칭=축분리
 9. [인성   ] 스트레스 상황에서 감정을 조절하는 본인만의 방법은?
      └ id=q00521 type=인성 region=경기도 job=None 신뢰도=무라벨 연도=미상 매칭=축분리
10. [상황형  ] 현업 부서(상사)가 업무 편의를 위해 보안 규정 예외(USB 사용, 망분리 우회, 자료 반출)를 요구한다.…
      └ id=q03019 type=상황형 region=None job=전산직 신뢰도=빈출 연도=미상 매칭=축분리
11. [마무리 ] 마지막으로 하고 싶은 말씀이 있으면 해 주세요. (WRAPUP)
------------------------------------------------------------------------
진단 (유형별 충족 / 완화단계):
  - 인성: 2/2  완화단계=축분리
  - 공직가치: 2/2  완화단계=축분리
  - 직무: 3/3  완화단계=축분리
  - 지역현안: 2/2  완화단계=축분리
  - 상황형: 1/1  완화단계=축분리
========================================================================
```

`매칭` / `완화단계` 라벨: **지역+직렬**(1순위 교차) · **축분리**(2순위) · **공통**(3순위).

---

## 4. 한계 (프로토타입 범위)

1. **중복 제거가 근사치**: 실제 설계는 임베딩 유사도 ≥0.9지만, 표준 라이브러리 제약으로
   정규화 텍스트 완전일치만 제거한다. 의미상 유사(다른 표현) 중복은 남을 수 있다 → v1에서 Vector Index 연동 필요.
2. **LLM 생성 보충 미구현**: 쿼터 미충족 시 `shortfall`만 표시하고 실제 생성은 하지 않는다.
   실제 시스템은 질문생성-프롬프트-템플릿 §2·§3으로 생성 후 품질 게이트를 거친다.
3. **region 라벨 오염 미정규화**: `중소시군-3차`, `군단위-호남` 등 배치 라벨이 region 값에 유입돼 있다(리포트 §3-2).
   프로토타입은 표준 행정구역명 정규화 매핑을 적용하지 않으므로, `--region`은 questions.json의 원본 값과 정확히 일치해야 매칭된다.
4. **발표/스피치 제시문 미포함**: 개별면접 큐만 구성한다. 발표 제시문(`type=발표`)은 별도 풀에서 1건 샘플링해야 하나 이 프로토타입 범위 밖.
5. **꼬리질문/사전조사서 추적 질문 미포함**: INTERVIEW 내부 루프(T1~T7 트리거)와 사전조사서 기반 추적 질문은 세션 오케스트레이터의 역할로, 여기서는 다루지 않는다.
6. **약점 보정 샘플링 미구현**: 이전 세션 '하' 판정 유형 +1 오버샘플링은 미반영(`recent_ids`로 재출제 억제만 지원).
7. **초급 모드 고신뢰 폴백**: 좁은 완화단계에 고신뢰 후보가 부족하면 저신뢰 라벨을 허용한다(하드 필터가 아닌 '우선' 정책).

---

## 5. 검증 결과 (3개 조합)

`seed=42`, 지방직 표준 트랙, 실전 모드 기준:

| 조합 | 쿼터 충족 | 지역현안 출처 | 직무 출처 | 비고 |
|---|---|---|---|---|
| 서울특별시 · 일반행정직 | 10/10 | 서울 지역축 | 일반행정 직렬축 | 서울 프로파일(인성3·지역현안1) 자동 적용, 오프닝=서울 교차 인성 |
| 부산광역시 · 사회복지직 | 10/10 | 부산 지역축(기장·엑스포) | 사복 직렬축(아동학대·장기요양) | 교차 태깅 0건이나 축 분리 조합으로 정상 구성 |
| 경기도 · 전산직 | 10/10 | 경기 지역축 | 전산 직렬축(G-클라우드·데이터기반행정) | 상황형=전산 보안규정 압박형(직렬 특화) |

- 세 조합 모두 유형 밸런스가 쿼터와 정확히 일치하고, 지역현안은 지역 축, 직무는 직렬 축에서 정확히 매칭됐다.
- 결정성(동일 seed 재현), seed 변경 시 다른 세트, 국가직 트랙의 region 제외/상황형 강화, 부족분 `shortfall` 경고, 존재하지 않는 지역의 공통(3순위) 폴백까지 동작 확인.


---

# 채점 엔진 프로토타입 (scorer.py)

공무원 AI 면접 MVP의 **채점(평정) 엔진** 프로토타입. 설계 문서(`채점-프롬프트-실장.md`
§1·§2, `평가루브릭-설계.md` §1-2·§2)의 채점 스키마·앙상블 집계 로직을 **표준 라이브러리만으로**
실행 가능하게 구현했다. API 키 없이 동작(Mock), 난수 없이 결정적.

> **주의**: `MockScorer`는 답변 길이·키워드·red flag 표현을 규칙으로 감지하는 **근사 채점기**로,
> **실제 채점 품질이 아니라 파이프라인(채점 → 집계 → 피드백) 데모**용이다. '하'는 미흡 보수
> 판정 원칙(루브릭 §1-3)에 따라 **red flag 표현 감지로만** 부여하며, 실제 판정은 §1 채점
> 프롬프트로 호출하는 LLM 채점기가 담당한다.

## S-1. 사용법

```bash
# 골든셋 회귀(축소판) 검증 실행 — 우수/보통/미흡 채점 확인
python3 scorer.py --selftest

# 위원 트랙 지정(2인 = 표준+엄격 / 3인 = 표준+엄격+직무)
python3 scorer.py --selftest --committees J-STD,J-STR

# 임의 답변 즉석 채점
python3 scorer.py --question "청렴이 중요한 이유?" \
                  --answer "규정에 조금 어긋나더라도 융통성 있게 받아도 된다고 생각합니다." --json
```

프로그램 임포트:

```python
import scorer

# 1) 단일 답변 채점 (위원 1인) → 채점-프롬프트-실장.md §1-4 스키마 JSON
sc = scorer.score_answer(question, answer, committee_id="J-STR",
                         written_task=None, prev_answers=None, question_type="상황형")

# 2) 세션 채점 (여러 문항 × N위원 → 과반수 집계)
items = [{"qid": "Q9", "type": "상황형", "question": q, "answer": a}]
session = scorer.score_session(items, committee_ids=("J-STD", "J-STR", "J-JOB"))
print(session["final_grade"], session["element_verdicts"])

# 3) 위원 N명 결과 → 과반수 종합 (§2-2 로직 직접 호출)
agg = scorer.aggregate_verdicts(results, N=3)  # results[committee_id][answer_id] = 채점 JSON
```

## S-2. 구성 요소

| 요소 | 역할 | 원천 |
|---|---|---|
| `LLMClient` (추상) | 실제 LLM 채점기가 구현할 인터페이스 (`score(...)`) | §1 프롬프트 |
| `MockScorer` | 규칙 기반 데모 채점기 (길이·키워드·red flag) | 골든셋 앵커 |
| `score_answer(...)` | 위원 1인 × 답변 1개 → §1-4 스키마 JSON | §1-4 |
| `aggregate_verdicts(...)` | 위원 N명 → 과반수 규칙으로 우수/보통/미흡 | §2-2 |
| `score_session(...)` | 여러 문항 × N위원 채점 + 세션 집계 | §2-1 |
| `run_golden_regression()` | 골든셋 3 triad(우수/보통/미흡) 회귀 | 부록 §6 |

## S-3. 채점 규칙 (MockScorer)

1. **red flag 표현 감지 → 해당 요소 강제 '하'** (하드 트리거). 표현 테이블은 골든셋 미흡
   앵커에서 추출(반공직·위법정당화·은폐책임전가·타인비하·답변포기 + 서면 대비 진술모순).
2. **강제되지 않은 요소**: (요소별 긍정 키워드 신호 ≥ 2) AND (발화 길이 ≥ 150자, 공백·괄호지문
   제외) → **'상'**, 그 외 **'중'**. 즉 '하'는 red flag 로만 나오고, 짧은 답변·긴장은 감점하지 않는다.
3. `member_grade` = §1-4 위원 개인 규칙(전부 상→우수 / 하 1개+ → 미흡 / 그 외 보통).
4. 근거(`evidence`)는 답변 원문에서 키워드/트리거를 포함한 문장을 인용(환각 방지 근사).
5. **위원 페르소나**: 규칙 공유 원칙에 따라 red flag 동작은 3위원 동일. (Mock에서는 기질 차이를
   등급에 반영하지 않음 — 실제 편차는 LLM 채점기 페르소나가 만든다.)

## S-4. 집계 로직 (aggregate_verdicts — §2-2 구현)

- `majority = N//2 + 1` (2인→2, 3인→2, 4인→3).
- 위원별 세션 요소판정 매트릭스 구성 → 요소별 최빈값(동률 시 보수적으로 상위 rank).
  단 **red flag 가 걸린 요소는 '하' 고정**.
- **우수**: 4요소 모두 '상'인 위원 수 ≥ 과반.
- **미흡 (a)**: 2개 이상 요소에 '하'를 준 위원 수 ≥ 과반. **(b)**: 동일 1요소에 '하'를 준
  위원 수 ≥ 과반.
- **보통**: 그 외 전부 (red flag 미발화 시 자동으로 보통 → 미흡 보수 판정 원칙 보존).

---

# 피드백 리포트 생성기 (feedback_report.py)

확정된 채점 결과(`scorer.score_session` 출력)를 **재채점 없이** 응시자용 마크다운 리포트로
렌더한다(`채점-프롬프트-실장.md` §4). 등급/요소판정을 바꾸지 않고 근거 인용과 코칭 텍스트만
조립하며, 비언어·스피치는 등급과 분리해 코칭 채널로만 노출한다.

## F-1. 사용법

```bash
python3 feedback_report.py        # 골든셋 Q9 미흡 답변으로 리포트 데모 출력
```

```python
import scorer, feedback_report
session = scorer.score_session(items, committee_ids=("J-STD", "J-STR"))
md = feedback_report.generate_report(session)   # 마크다운 문자열
```

## F-2. 리포트 구성 (§4-3 스키마 → 마크다운)

1. **종합 등급** + 등급 설명(과반수 규칙·red flag 유무를 응시자 언어로) + 요소별 대표 판정 표.
2. **강점** — '상' 요소를 근거 인용과 함께.
3. **개선점** — '하'는 red flag note + 원문 인용 + 교정 방향, '중'은 구체성 보강 안내.
4. **모범답변 방향** — 대본이 아닌 뼈대(두괄식→근거→적용 / 상황형 4단계).
5. **스피치 코칭 (등급 미반영 · 스텁)** — 발화 길이·필러·침묵을 텍스트에서 근사 산출.
6. **다음 연습 질문** — '하'/'중' 요소를 보강하는 유형으로 최대 3개(약점 보정).
7. **마무리 격려** — 합격 보장 표현 금지, 존댓말·격려체.

## F-3. 스텁 명시

- **스피치 코칭은 규칙 기반 스텁**: 실제 음성 분석(CPM·필러·침묵·response latency, 루브릭
  §3-2)을 대체하지 않는다. 여기서는 전사문 글자수로 발화 시간을 근사 추정할 뿐이다.
- **문장 조립도 근사치**: 실제 서비스는 §4 피드백 LLM(Sonnet급)이 근거를 자연어로 재서술한다.

---

# 실제 LLM 채점 연결 지점 (프로토타입 → v1 교체 포인트)

Mock을 실제 LLM로 바꾸는 지점을 명시한다. **`MockScorer`를 `LLMClient` 하위의 실제 구현체로
교체**하면 나머지 파이프라인(집계·리포트)은 그대로 재사용된다.

1. **채점기 교체 (핵심)**: `LLMClient.score(...)`를 구현한 `AnthropicScorer` 등을 작성.
   - System 프롬프트 = `채점-프롬프트-실장.md` §1-1 + `{{FEWSHOT_BLOCK}}`(§5 조립) + §1-3
     `{{PERSONA_BLOCK}}`(committee_id 별).
   - User 프롬프트 = §1-2 슬롯 채우기(`question`, `answer`, `written_task`, `prev_answers`,
     `region_context`).
   - 응답은 §1-4 JSON 스키마로 파싱 → `score_answer(..., client=AnthropicScorer(cid))`에 주입.
   - `evidence` 빈 배열이면 무효 → 재채점 요청(§1-4 단서).
   - temperature 0.0~0.2 권장, 루브릭+few-shot 프리픽스 캐싱(아키텍처 §2-3-3).
2. **red flag 2차 판정기(선택)**: §3 경량 모델(Haiku급) 탐지기를 별도 호출해 `red_flags`를
   보강하고, `aggregate_verdicts`의 하드 트리거 입력으로 합류. (현재 Mock은 §1 채점기 안의
   red flag 필드만 사용.)
3. **집계는 코드 그대로**: `aggregate_verdicts`는 LLM 결과에도 동일 적용(제도 규칙 = 결정적 코드).
4. **피드백 생성기 교체**: `feedback_report.generate_report`의 문장 조립을 §4 피드백 LLM 호출로
   대체 가능. 단 **등급/요소판정은 입력값 그대로 사용**(재채점 금지)하고 스피치는 등급 분리 유지.
5. **스피치 지표 연결**: `_speech_metrics` 스텁을 실제 STT + 음성 분석(CPM·필러·침묵) 산출로 교체.
6. **회귀 게이트**: 채점기/프롬프트/few-shot 변경 시 `run_golden_regression()`(→ 골든셋 60개
   전체로 확장)으로 등급 뒤집힘·트리거 재현율·요소 일치율을 검증(부록 §6 통과 기준).

## 검증 결과 (골든셋 회귀 축소판)

`python3 scorer.py --selftest` (3인 앙상블 J-STD·J-STR·J-JOB, 과반=2):

| Q | 유형 | 기대 | 판정 | 일치 | 요소판정(소/헌/창/윤) · red flag |
|---|---|---|---|---|---|
| Q1 | 공직가치 | 우수 | 우수 | OK | 상상상상 · - |
| Q1 | 공직가치 | 보통 | 보통 | OK | 중중중중 · - |
| Q1 | 공직가치 | 미흡 | 미흡 | OK | 중하중하 · 반공직가치관 |
| Q6 | 인성 | 우수 | 우수 | OK | 상상상상 · - |
| Q6 | 인성 | 보통 | 보통 | OK | 중중중중 · - |
| Q6 | 인성 | 미흡 | 미흡 | OK | 하하중중 · 타인비하비협조 |
| Q9 | 상황형 | 우수 | 우수 | OK | 상상상상 · - |
| Q9 | 상황형 | 보통 | 보통 | OK | 중중중중 · - |
| Q9 | 상황형 | 미흡 | 미흡 | OK | 중중하하 · 위법정당화, 은폐책임전가 |

- **등급 정확도 9/9 (100%)**. 3개 triad(반공직 / 타인비하 / 위법정당화+책임전가)로 주요
  red flag 계열을 커버. 우수는 전 요소 '상', 보통은 '하' 없음, 미흡은 red flag 로 '하' 발생 →
  등급이 골든셋 기대 레이블과 일치.
- 요소별 '하' 위치도 골든셋 해설과 정합(Q1 미흡=헌신·윤리 하, Q9 미흡=창의·윤리 하 등).
- 한계: 우수/보통 분리는 **길이 게이트(150자) + 키워드 신호**에 의존하는 근사치다. 경계
  답변(짧지만 우수, 길지만 공허)은 오판할 수 있으며, 이는 v1의 LLM 채점기가 해결할 몫이다.

---

# 세션 오케스트레이터 프로토타입 (session_engine.py)

`question_selector.py` 위에 얹는 **면접관 대화 엔진(세션 상태 머신)** 프로토타입.
질문 큐를 순회하며 페르소나(위원A/B/C)가 발화하고, 각 답변마다 규칙 기반으로 꼬리질문
트리거(T1/T3/T4/T5/T6/T7)를 판정해 꼬리질문을 이어간다. **표준 라이브러리만** 사용,
**API 키 없이**(MockLLMClient) **결정적**으로 실행된다.

설계 근거: `data/06-answer-guides/모의면접-세션-설계.md` §2(상태 머신·트리거),
`data/08-system/면접관-페르소나-세트.md`(3인 페르소나·압박계수),
`data/07-structured/region_context.json`·`job_context.json`(컨텍스트 주입).

## SE-1. 상태 머신

```
INTAKE ─→ SPEECH_PREP ─→ SPEECH ─→ INTERVIEW ─→ WRAPUP ─→ SCORING(스텁)
  │            │            │          │            │           │
  │            │            │          │            │           └ 로그 집계→채점 파이프라인 연결점
  │            │            │          │            └ "마지막으로 하고 싶은 말" 1문
  │            │            │          └ 질문 큐 순회 + 꼬리질문 루프(아래)
  │            │            └ 스피치 발표(서울 5분/부산 3분, 컨텍스트 제시문)
  │            └ 스피치 제시문 검토(지역현안 소재)
  └ 트랙·지역·직렬·난이도·압박계수 확정 + 컨텍스트 반영 오프닝

INTERVIEW 내부 루프 (각 주질문마다):
  ASK(주질문, 유형별 페르소나) → LISTEN(답변)
    → detect_trigger(답변)                     # 규칙 기반, 우선순위 T1>T3>T4>T5>T6>T7 중 1개
        ├ 트리거 有 & depth<max & 예산 有 & 압박계수 게이트 통과
        │     → FOLLOWUP(트리거→페르소나 발화) → LISTEN → (같은 트리거로 재판정) ↺
        └ 트리거 無 / 뎁스소진 / 예산소진 / 압박형 스킵 → NEXT_QUESTION
```

**꼬리질문 트리거(규칙 기반 스텁)** — 실제 설계의 "경량 LLM 1회 분석"을 키워드/휴리스틱으로 근사:

| 트리거 | 감지(키워드/휴리스틱) | 발화 페르소나 | 최대 뎁스 |
|---|---|---|---|
| T1 red flag | "규정을 유연", "봐주", "사익" 등 반공직 신호 | 압박형(위원C) | 1 |
| T3 경험주장 | "경험이 있습니다", "봉사", "이끌었" | 온화형(위원A) | 3 |
| T4 추상어 | "최선을 다", "열심히", "소통하겠" | 온화형(위원A) | 2 |
| T5 정책·수치 | 컨텍스트 정책 토큰 / 숫자+단위 정규식 | 표준형(위원B) | 2 |
| T6 원칙답변 | 상황형에서 "법령/규정 확인", "재검토 건의" | 압박형(위원C) | 3 |
| T7 미완결 | 15자 미만 / "잘 모르겠습니다" | 온화형(위원A) | 1 |

- 우선순위 최상위 1개만 실행(§107). T2(진술모순)는 세션로그 의미 대조가 필요해 이 프로토타입에서는 제외.
- **압박계수 게이트**: 압박형 트리거(T1/T6)는 지자체 압박계수 확률로만 발화(서울 0.4·부산 0.2·대구 0.7·경기 0.9). 2인 트랙(서울·부산)은 위원C 미투입 → 표준형이 검증 기능 흡수(로그에 "흡수" 표기).
- **초급 모드**: T1·T7만, 최대 뎁스 1(설계 §4-1).
- **꼬리질문 예산**: 총 주질문의 60%(≈시간예산 40% 근사) 초과 시 이후 트리거는 통과 처리.

## SE-2. LLMClient 인터페이스 — 실제 Claude API 연결 지점

세션 엔진은 면접관 발화를 **오직 `LLMClient` 프로토콜**을 통해서만 얻는다. 엔진 코드를
바꾸지 않고 발화 백엔드만 교체할 수 있다.

```python
class LLMClient(Protocol):
    def interviewer_turn(self, kind, *, persona=None, context=None, question=None,
                         answer=None, trigger=None, snippet=None, depth=0) -> str: ...
    #  kind ∈ {intro, speech_prompt, speech_ack, main, followup, wrapup, closing}
```

- **`MockLLMClient`(기본)**: 페르소나별 말투·트리거별 대사를 템플릿으로 재현. API 키 불필요·결정적. 데모/오프라인 개발용.
- **`AnthropicLLMClient`(연결 지점, 하단 주석)**: `MockLLMClient` 자리에 주입하면 실제 Claude 발화로 교체된다. 구현 시:
  1. 페르소나별 **시스템 프롬프트** = 페르소나-세트.md §1-1/1-2/1-3 프롬프트 + **§5 하드 가드레일**(블라인드·차별·인신공격·사실날조 금지).
  2. `context`(지역/직렬 자료)를 `[지자체 컨텍스트]`/`[직렬 컨텍스트]`로 주입 → 자료 밖 정책·수치 생성 차단.
  3. 꼬리질문 **temperature 0.3**(답변 인용 정확성 우선, §3).

  `session_engine.py`의 `AnthropicLLMClient.interviewer_turn()` 본문에 `★★★ 실제 LLM(Claude) 연결 지점 ★★★` 주석과 `messages.create(...)` 호출 스켈레톤이 표시돼 있다.

## SE-3. 컨텍스트 주입

`region_context.json`/`job_context.json`을 세션에 주입해:
- **오프닝**(INTAKE): 지역 슬로건·시정비전 + 직렬 주요업무를 반영한 환영 멘트.
- **스피치 제시문**(SPEECH_PREP): 지역현안 1건을 소재로 사용.
- **지역현안 주질문**(INTERVIEW): 지역현안 한 문장을 주질문 앞에 얹음.
- **T5 감지 키워드**: 지역 핵심사업/현안 + 직렬 핵심제도에서 토큰을 추출해 정책 언급 판정에 사용.

가드레일: 컨텍스트에 **있는 사실만** 소재로 쓴다(자료 밖 정책명·수치 생성 금지).

## SE-4. 사용법

```bash
# 데모 자동 실행(미리 정의된 답변으로 트리거 전부 시연)
python3 session_engine.py --region 서울특별시 --job 일반행정직
python3 session_engine.py --region 부산광역시 --job 소방직

# 압박형(위원C) 발화 확인용 고압박 프로파일 / 초급 모드
python3 session_engine.py --region 경기도 --job 일반행정직           # 압박계수 0.9, 3인
python3 session_engine.py --region 서울특별시 --job 일반행정직 --difficulty 초급

# 실제 사용자 입력(stdin)으로 진행
python3 session_engine.py --region 서울특별시 --job 일반행정직 --interactive
```

| 옵션 | 기본 | 설명 |
|---|---|---|
| `--region` / `--job` | (필수) | 지자체·직렬 (예: 서울특별시 / 일반행정직) |
| `--track` | 지방직표준 | `지방직표준` \| `국가직9급` |
| `--difficulty` | 실전 | `실전`(T1~T7) \| `초급`(T1·T7, 뎁스1) |
| `--seed` | 42 | 질문선택+압박계수 게이트 재현 시드 |
| `--interactive` | off | stdin 답변 입력(기본은 데모 자동 답변) |

## SE-5. 데모 실행 흐름 (발췌)

```
[t001][INTAKE][진행] 서울특별시 일반행정직 면접에 오신 것을 환영합니다. … 서울특별시는 '다시 뛰는 공정도시 서울'을(를) 시정 기조로 …
[t002][SPEECH_PREP][진행] [스피치 제시문] '저출생'에 대한 본인의 생각을, 5분 내외로 발표해 주세요. …
[t005][INTERVIEW][위원A/온화형] 네, 편하게 말씀하셔도 됩니다. 사회생활을 하면서 겪은 갈등 상황과 해결 방법은?
        (지원자) 학창 시절 봉사 동아리 회장으로 팀을 이끈 경험이 있습니다. …
   ↳ [트리거 T3 경험주장(STAR) 감지: '경험이 있습니다' → 위원A 꼬리질문 (뎁스 1/3)]
[t008][INTERVIEW][위원A/온화형] 좋은 경험이네요. 그때 본인이 맡았던 역할은 무엇이었어요?
        …
[t020][INTERVIEW][위원B/표준형] 그럼 여쭙겠습니다. 관심 있는 서울시 정책 분야는? …
        (지원자) 민원인이 많이 힘들어 보이면 규정을 조금 유연하게 적용해서라도 …
   ↳ [트리거 T1 red flag(소명) 감지 · 압박계수 0.4 · roll=0.81 → 스킵]   # 2인 저압박 재현
…
[SCORING · 스텁] 실제 채점은 평가루브릭-설계.md §4-3 파이프라인 연결 지점
  · 주질문 10개, 꼬리질문 5개(예산 6), 총 발화 44턴
  · 트리거 발동: T3×2, T4×1, T5×1, T7×1
  · 참여 위원: 위원A(온화형)·위원B(표준형) / 판정 규칙: 만장일치(2인)
```

고압박 프로파일(경기 0.9, 3인)에서는 동일 seed의 roll=0.81 < 0.9 이므로 **위원C(압박형)가 T1 소명질문을 실행**한다:

```
   ↳ [트리거 T1 red flag(소명) 감지: '규정을 조금 유연' → 위원C 꼬리질문 (뎁스 1/1) · 압박계수 0.9 · roll=0.81 → 실행]
[t023][INTERVIEW][위원C/압박형] 방금 '규정을 조금 유연'(이)라고 하셨는데, 그렇게 판단하신 근거는 무엇입니까? 다른 민원인과의 형평성 문제는 어떻게 보시는지요?
```

## SE-6. 검증 결과

| 시나리오 | 확인 내용 |
|---|---|
| 서울 · 일반행정직 (2인, 0.4) | 컨텍스트 오프닝, T3(뎁스2)·T4·T5·T7 발화, T1/T6는 압박계수로 스킵(표준형 흡수 트랙) |
| 부산 · 소방직 (2인, 0.2) | 소방 직렬축 질문, T3·T4·T5×2·T7 발화, 압박형 트리거 스킵, 예산 소진 통과 |
| 경기 · 일반행정직 (3인, 0.9) | 위원C 활성, T1 소명질문 **실행**, 2/3 다수결 표기 |
| 서울 · 초급 모드 | T1·T7만 허용(T3~T6 억제), 뎁스 1 |
| 동일 seed 2회 | 출력 완전 동일(결정적) |

## SE-7. 한계 (프로토타입 범위)

1. **트리거 판정이 키워드 휴리스틱**: 실제는 경량 LLM 1회 분석. T2(진술모순)는 세션로그 의미 대조가 필요해 미구현.
2. **꼬리질문/발화가 템플릿**: `MockLLMClient`는 규칙 문장. 실제 발화·컨텍스트 인용 정확도는 `AnthropicLLMClient` 연결 후 확보.
3. **SPEECH_QA·PREWORK(사전조사서) 축약**: 스피치 후속질의·사전조사서 기반 추적질문(T2 대질)은 큐에 미포함.
4. **SCORING은 스텁**: 로그 신호 집계만. STT 스피치지표·페르소나 앙상블 채점(scorer.py 연결)·과반 집계·FEEDBACK은 평가루브릭-설계.md §4-3 연결점으로 남김.
5. **압박계수 게이트가 확률 스킵**: 발화 빈도 배수를 단일 확률로 근사(실제는 트리거 종류별 가중 가능).

---

# 통합 데모 파이프라인 (demo_pipeline.py)

위 4개 프로토타입(`question_selector` · `session_engine` · `scorer` · `feedback_report`)을
**한 번의 실행으로 잇는** 엔드투엔드 데모. 질문 선택 → 면접 진행(MockLLM 자동 답변) →
각 답변 채점(MockScorer) → 위원 앙상블 집계 → 피드백 리포트까지 **표준 라이브러리만으로,
API 키 없이, 결정적으로** 완주한다. 원본 4개 모듈은 수정하지 않고, 모듈 간 시그니처가
맞지 않는 지점만 이 파일 안의 **어댑터 함수**로 이어 붙인다.

## D-1. 전체 파이프라인 다이어그램

```
questions.json ─┐
                ▼
 [1] question_selector.select_questions(region,job,track,difficulty,seed)
        └─> plan = { seq:[{phase,tier,question:{id,type,text,...}}], quota, diagnostics }
                │           (질문 원문·유형·출제순서의 단일 출처)
                ▼
 [2] session_engine.SessionEngine(..., llm=MockLLMClient, provider=DemoAnswerProvider).run()
        │  INTAKE→SPEECH→INTERVIEW(주질문+꼬리질문 트리거)→WRAPUP→SCORING(스텁)
        └─> log = [{t,state,role(면접관/지원자/시스템),persona,qid,trigger,text}, ...]
                │
                │   ── 어댑터 1: _build_scoring_items(plan, log) ─────────────────
                │      plan.seq(원문/유형/순서) + log(지원자 발화)를 결합해
                │      [{qid,type,question,answer}] 로 변환. answer 는 같은 qid 의
                │      주답변+꼬리질문 답변을 순서대로 이어 붙인 '답변 스레드'.
                │   ── 어댑터 2: _committee_ids_for(engine.personas) ─────────────
                │      면접 위원 수(2인/3인)에 맞춰 채점 위원 앙상블 규모 결정.
                ▼
 [3] scorer.score_session(items, committee_ids)   ← 위원 N인 × 문항별 §1-4 채점
 [4]   └─ 내부 aggregate_verdicts(과반 규칙) = '위원 앙상블 집계'
        └─> session_result = { results, aggregate, element_verdicts, final_grade, ... }
                ▼
 [5] feedback_report.generate_report(session_result)  ← 재채점 없이 마크다운 렌더
        └─> 응시자용 피드백 리포트(stdout, --save 시 파일)
```

`session_engine` 자체의 SCORING 상태는 **로그 신호 집계 스텁**이다. 데모 파이프라인은 그
연결점을 실제 `scorer` → `feedback_report` 호출로 **대체**한다(엔진 SCORING 스텁 출력은
전환 지점 참고용으로 그대로 노출된다).

## D-2. 어댑터가 메운 시그니처 간극 (원본 무수정)

| 간극 | 원인 | 해결(어댑터) |
|---|---|---|
| 세션 로그 ↔ 채점 입력 | `session_engine`은 `log`(발화 dict 스트림)를 내보내고, `scorer`는 `[{qid,type,question,answer}]`를 받는다 | `_build_scoring_items(plan, log)` — 로그의 지원자 발화를 qid로 그룹핑하고, 질문 원문/유형은 `plan["seq"]`에서 가져와 결합 |
| 질문 원문 출처 | 로그의 면접관 발화는 페르소나 어조(예: "네, 편하게 말씀하셔도…")가 덧입혀져 **원문이 아님** | 채점용 `question`은 로그가 아니라 `plan["seq"]`의 `question.text`에서 취함 |
| 답변 단위 불일치 | scorer는 문항당 답변 1개를 채점하는데, 한 주질문에 주답변+꼬리질문 답변이 여럿 | 같은 qid의 지원자 발화를 로그 순서대로 이어 붙여 '답변 스레드' 1개로 만들어 문항당 1답변으로 정규화 |
| 면접 위원 수 ↔ 채점 위원 수 | `session_engine` 페르소나 로스터(2인/3인)와 `scorer` 위원 앙상블이 별개 인자 | `_committee_ids_for(personas)` — 2인→`(J-STD,J-STR)`, 3인→`+J-JOB`로 정렬 |

이 4가지 외에는 각 모듈의 공개 함수 시그니처를 그대로 호출한다(`qs.select_questions`,
`se.SessionEngine(...).run()`, `sc.score_session`, `fr.generate_report`).

## D-3. 사용법

```bash
# 기본 (지방직 표준, 실전 모드, seed=42) — 전 단계 로그 + 피드백 리포트를 stdout에
python3 demo_pipeline.py --region 서울특별시 --job 일반행정직

# 3인 트랙(고압박) — 위원C 압박형 T1 소명질문 실행 + 채점 위원 3인
python3 demo_pipeline.py --region 경기도 --job 일반행정직

# 국가직9급 트랙 / 초급 난이도 / 시드 지정
python3 demo_pipeline.py --region 서울특별시 --job 일반행정직 --track 국가직9급
python3 demo_pipeline.py --region 부산광역시 --job 소방직 --difficulty 초급 --seed 7

# 리포트를 파일로 저장(--save, 경로 생략 시 feedback_<지역>_<직렬>_seed<N>.md 자동 생성)
python3 demo_pipeline.py --region 대구광역시 --job 일반행정직 --save
python3 demo_pipeline.py --region 대구광역시 --job 일반행정직 --save /path/to/report.md
```

| 옵션 | 기본 | 설명 |
|---|---|---|
| `--region` / `--job` | (필수) | 지자체·직렬 (예: 서울특별시 / 일반행정직) |
| `--track` | 지방직표준 | `지방직표준` \| `국가직9급` |
| `--difficulty` | 실전 | `실전` \| `초급` |
| `--seed` | 42 | 질문선택+압박계수 게이트 재현 시드 |
| `--save [PATH]` | off | 피드백 리포트를 마크다운 파일로 저장(경로 생략 시 자동 파일명) |

프로그램 임포트도 가능:

```python
import demo_pipeline as dp
session_result, report_md = dp.run_pipeline("서울특별시", "일반행정직",
                                            track="지방직표준", difficulty="실전", seed=42)
print(session_result["final_grade"])   # 종합 등급
# report_md = 응시자용 피드백 마크다운
```

## D-4. 샘플 출력 (발췌)

```
##############################################################################
#  단계 1 · 질문 선택 (question_selector.select_questions)
##############################################################################
쿼터: 공직가치2  인성3  직무3  지역현안1  상황형1  (합계 10)
선택된 주질문 10개 (유형 순):
   1. [오프닝  ] 사회생활을 하면서 겪은 갈등 상황과 해결 방법은?   (id=q01013 type=인성)
   ...

##############################################################################
#  단계 2 · 면접 진행 (session_engine.SessionEngine.run · MockLLMClient)
##############################################################################
[t005][INTERVIEW][위원A/온화형] 네, 편하게 말씀하셔도 됩니다. 사회생활을 하면서 겪은 갈등 상황과…
        (지원자) 학창 시절 봉사 동아리 회장으로 팀을 이끈 경험이 있습니다. 그때 정말 열심히 했습니다.
   ↳ [트리거 T3 경험주장(STAR) 감지: '경험이 있습니다' → 위원A 꼬리질문 (뎁스 1/3)]
   ... (INTAKE→SPEECH→INTERVIEW 꼬리질문→WRAPUP 전체 전사)

##############################################################################
#  단계 3·4 · 각 답변 채점 + 위원 앙상블 집계 (scorer.score_session · MockScorer)
##############################################################################
채점 위원 앙상블: J-STD, J-STR (N=2, 과반=2)
문항별 답변 스레드 → 위원별 개인등급:
  - q01013   [인성   ] 답변 130자 → 보통/보통
  ...
세션 대표 요소판정(소통/헌신/창의/윤리): 중 / 중 / 중 / 중
감지된 red flag 계열: 없음
종합 등급: 보통

##############################################################################
#  단계 5 · 피드백 리포트 생성 (feedback_report.generate_report)
##############################################################################
# 모의면접 피드백 리포트
- 문항 수: 10개 (유형: 공직가치, 상황형, 인성, 지역현안, 직무)
## 1. 종합 등급: **보통**
... (강점 / 개선점 / 모범답변 방향 / 스피치 코칭 / 다음 연습 질문 / 마무리)
```

## D-5. 검증 결과 (엔드투엔드 완주)

| 조합 | 트랙/위원 | 완주 | 채점 앙상블 | 종합 등급 |
|---|---|---|---|---|
| 서울 · 일반행정직 | 지방직표준 / 2인(0.4) | ✓ | J-STD·J-STR | 보통 |
| 경기 · 일반행정직 | 지방직표준 / 3인(0.9) | ✓ | J-STD·J-STR·J-JOB | 보통 |
| 부산 · 소방직 | 지방직표준 / 2인(0.2) | ✓ | J-STD·J-STR | 보통 |
| 서울 · 일반행정직 | 국가직9급 / 2인 | ✓ | J-STD·J-STR | 보통 |
| 대구 · 일반행정직 (seed 7, --save) | 지방직표준 / 3인 | ✓ | 3인 | 보통 |

- **결정성**: 동일 인자 2회 실행 결과가 완전히 동일(`diff` 무차이).
- **위원 수 연동**: 3인 트랙(경기)에서 위원C(압박형)가 T1 소명질문을 실행하고, 채점도 3인 앙상블로 자동 확장됨을 확인.
- **모듈 결합**: 질문 원문/유형은 `question_selector` → 답변은 `session_engine` 로그 → 채점/집계는 `scorer` → 렌더는 `feedback_report`로 값이 온전히 흘러감을 단계 로그로 확인.

> **관찰(정상 동작)**: 데모 5조합의 종합 등급이 모두 **보통**으로 나온다. 이는 버그가 아니라
> **두 프로토타입의 데모 어휘가 독립적으로 작성**됐기 때문이다. `session_engine`의 자동 답변
> T1 표현("규정을 조금 유연하게 적용")은 `scorer`의 red flag 패턴 테이블("규정에 조금 어긋나더라도",
> "유연하게 해석해서라도" 등)과 문자열이 겹치지 않아 red flag가 발화되지 않고, 답변이 짧아
> 150자 길이 게이트도 넘지 못한다 → 전 요소 '중' → 보수적 '보통'. 채점→집계→리포트 **뒷단
> 자체는 등급을 정상 판별**한다: 실제 red flag 표현이 담긴 답변을 같은 경로로 흘리면
> `final_grade=미흡`(red flag `위법정당화·은폐책임전가`)이 나오고, `scorer.py --selftest`의
> 골든셋 회귀는 우수/보통/미흡을 9/9로 구분한다. 실제 LLM 답변자로 교체하면 이 어휘 정합
> 문제는 사라진다.

## D-6. 실제 LLM 교체 시 바뀌는 지점

데모 파이프라인의 **연결 구조(어댑터·호출 순서)는 그대로 두고**, Mock 백엔드만 교체하면
실서비스 파이프라인이 된다. 바뀌는 지점은 각 모듈의 교체 포인트와 동일하다:

1. **면접관 발화** — `session_engine`의 `MockLLMClient` → `AnthropicLLMClient`
   (페르소나 시스템 프롬프트 + §5 가드레일, 꼬리질문 temp 0.3). `demo_pipeline.py`에서는
   `se.SessionEngine(..., llm=...)` 인자 한 줄만 교체.
2. **답변자** — 데모는 `DemoAnswerProvider`(대본). 실사용은 `StdinAnswerProvider`(사람 입력)
   또는 STT 파이프라인. `provider=` 인자만 교체.
3. **채점기** — `scorer`의 `MockScorer` → §1 프롬프트로 LLM을 호출하는 `LLMClient` 구현체.
   `score_session(...)` 내부 `score_answer(..., client=)`에 주입(집계 `aggregate_verdicts`는
   결정적 코드라 그대로 재사용).
4. **꼬리질문 트리거** — 키워드 휴리스틱(`detect_trigger`) → 경량 LLM 1회 분석으로 교체 시
   red flag/구체성 판정 재현율이 오르고, 위 D-5의 어휘 정합 한계가 해소됨.
5. **피드백 문장** — `feedback_report.generate_report`의 규칙 조립 → §4 피드백 LLM(Sonnet급)
   재서술로 교체 가능. **단 등급/요소판정은 입력값 그대로**(재채점 금지), 스피치는 등급 분리 유지.
6. **스피치 지표** — `feedback_report._speech_metrics` 스텁(글자수 기반) → 실제 STT + 음성
   분석(CPM·필러·침묵)으로 교체.

어댑터 2개(`_build_scoring_items`, `_committee_ids_for`)는 **데이터 형태 변환**이라 Mock↔실제
교체와 무관하게 유지된다(단, 실제 STT 답변도 동일하게 qid별 스레드로 묶이면 그대로 동작).


---

# 실제 Claude API 어댑터 (llm_client.py)

프로토타입의 Mock 백엔드를 **실제 Claude(Anthropic API)** 로 교체하는 어댑터. 원본 4개 모듈은
한 줄도 수정하지 않고, 각 모듈이 요구하는 인터페이스를 그대로 구현한 클라이언트를 주입한다.

- `AnthropicInterviewerClient` — 면접관 발화·꼬리질문 생성 (`session_engine.LLMClient` 프로토콜 구현).
  페르소나 시스템 프롬프트(면접관-페르소나-세트.md §1) + 하드 가드레일(§5) + 지자체/직렬 컨텍스트 주입.
  경량 트리거 판정 `detect_trigger()`(§3)도 제공 — `session_engine`의 키워드 휴리스틱 대체.
- `AnthropicScorerClient` — 채점 (`scorer.LLMClient` 인터페이스 구현).
  채점-프롬프트-실장.md §1 System/User 프롬프트 + §1-4 JSON 스키마(structured outputs) + §1-3 위원 페르소나.
  red flag 2차 판정 `detect_red_flags()`(§3)도 제공.

## L-1. 환경변수 설정

```bash
export ANTHROPIC_API_KEY="sk-ant-..."     # 실제 호출에만 필요(드라이런은 불필요)
pip install anthropic                       # SDK. 미설치 시 import/조립/드라이런은 되고, 실제 호출만 막힌다
```

- 키가 없으면 **실제 호출 시점**에 한국어 에러(`환경변수 ANTHROPIC_API_KEY 가 설정되어 있지 않습니다 …`).
- `anthropic` 미설치면 실제 호출 시점에 `pip install anthropic` 안내 에러. import·인스턴스화는 정상.

## L-2. 역할별 모델 매핑 (정확 모델 ID)

| 역할 | 모델 ID | 선택 이유 |
|---|---|---|
| 면접관 대화 | `claude-sonnet-5` | 수십 턴의 짧은 페르소나 발화를 낮은 지연·비용으로 자연스럽게 |
| 트리거/경량 판정 | `claude-haiku-4-5-20251001` | 답변당 1회 도는 이진 트리거 탐지 — 속도·저비용 우선 |
| 채점 앙상블 | `claude-opus-4-8` | 합격/미흡 임계 판정. reasoning→verdict 최상위 판단력, 위원 N회 호출 |

현행 모델 API 제약(claude-api 스킬 반영):
- `claude-sonnet-5`·`claude-opus-4-8` 은 `temperature`/`top_p`/`top_k` 를 받지 않는다(400).
  설계 문서의 "채점 temp 0.0~0.2 / 꼬리질문 temp 0.3" 권장은 **프롬프트 지시로 대체**한다.
  `temperature`(=0.0)는 sampling 을 허용하는 `claude-haiku-4-5-20251001`(경량 판정)에만 적용.
- `thinking`: 채점=adaptive(추론 품질), 면접 발화=disabled(짧아서 불필요), Haiku=미지정.
- 프롬프트 캐싱: `system` 프리픽스(가드레일+컨텍스트 / 루브릭+few-shot)에 `cache_control:{ephemeral}`.
  세션 내 동결되는 프리픽스를 캐시하고, 턴별로 바뀌는 페르소나/질문·답변은 그 뒤에 배치.

## L-3. 드라이런 실행

실제 호출 대신 **조립된 프롬프트(모델·파라미터·system·user)** 를 출력한다. 키·SDK 없이 동작한다.

```bash
python3 llm_client.py             # 드라이런(기본): 면접관 3종 + 트리거 + 채점 + red flag 프롬프트 조립 출력
python3 llm_client.py --live      # 실제 API 호출(anthropic 설치 + ANTHROPIC_API_KEY 필요)
```

프로그램 임포트로 프롬프트만 조립해 보기:

```python
import llm_client as lc
itv = lc.AnthropicInterviewerClient(dry_run=True)
print(itv.interviewer_turn("main", persona="표준형", context=ctx, question=q))  # 조립 프롬프트 문자열
req = itv.build_turn("followup", persona="압박형", context=ctx, trigger="T1", snippet="유연하게 적용", depth=1)
print(lc.render_request(req))   # {model, max_tokens, params, system[], messages[]} 렌더
```

## L-4. Mock → 실제 교체 방법

**세션 엔진 코드·채점 코드 무수정.** 주입 인자만 바꾼다.

```python
# 1) 면접관: MockLLMClient → AnthropicInterviewerClient
import llm_client as lc, session_engine as se
engine = se.SessionEngine(region="대구광역시", job="일반행정직",
                          llm=lc.AnthropicInterviewerClient())      # ← 이 한 줄만 교체
engine.run()

# 2) 채점: MockScorer → AnthropicScorerClient (위원별 1인 주입)
import scorer as sc
client = lc.AnthropicScorerClient(committee_id="J-STR")
result = sc.score_answer(question, answer, client=client, question_type="상황형")
# score_session 은 committee_id 별로 AnthropicScorerClient 를 만들어 score_answer(..., client=) 에 주입.
# 앙상블 집계 aggregate_verdicts 는 결정적 코드라 그대로 재사용(교체 불필요).

# 3) (옵션) 꼬리질문 트리거: 키워드 휴리스틱 detect_trigger → LLM 경량 판정
trig, snippet = lc.AnthropicInterviewerClient().detect_trigger(answer, qtype="공직가치", difficulty="실전")
```

- `demo_pipeline.py`에서는 `se.SessionEngine(..., llm=...)` 과 `score_session` 의 `client` 경로만
  실제 클라이언트로 바꾸면 그대로 실서비스 파이프라인이 된다(D-6 교체 포인트와 동일).
- `AnthropicScorerClient`는 `MockScorer`와 동일한 `committee_id`(J-STD/J-STR/J-JOB)와 `score(...)`
  시그니처를 갖는다 → `scorer.LLMClient` 드롭인.

## L-5. 검증 결과 (드라이런)

- `python3 llm_client.py` — 면접관 intro/main/followup(3종) + 경량 트리거(Haiku) + 채점(Opus,
  §1-4 스키마) + red flag(Haiku, §3) **6개 프롬프트가 모델·파라미터·캐시 경계까지 정확히 조립**됨을 확인.
- 모델 매핑: 발화=`claude-sonnet-5`(thinking disabled) / 트리거·red flag=`claude-haiku-4-5-20251001`
  (temperature 0.0 + JSON 스키마) / 채점=`claude-opus-4-8`(adaptive thinking + §1-4 structured outputs).
- 인터페이스 호환: `scorer.score_answer(..., client=AnthropicScorerClient(dry_run=True))` 정상 동작,
  `session_engine.LLMClient.interviewer_turn` 시그니처 일치.
- 안전장치: `anthropic` 미설치·`ANTHROPIC_API_KEY` 미설정 상태에서 import·조립·드라이런 완주,
  실제 호출 경로만 명확한 한국어 `RuntimeError`.
