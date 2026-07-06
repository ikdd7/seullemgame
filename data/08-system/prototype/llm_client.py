#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llm_client.py — 실제 Claude(Anthropic) API 어댑터 (프로토타입 → v1 교체 포인트)

이 모듈은 프로토타입의 Mock 백엔드를 실제 Claude로 교체하는 **어댑터**다.
원본 4개 모듈(session_engine.py / scorer.py / feedback_report.py / question_selector.py)은
한 줄도 바꾸지 않는다. 대신 각 모듈이 요구하는 인터페이스를 그대로 구현한 실제 API 클라이언트를
제공한다.

  ┌─ 면접관 발화·꼬리질문 ─ AnthropicInterviewerClient  (session_engine.LLMClient 프로토콜 구현)
  │      · interviewer_turn(kind, persona, context, question, answer, trigger, snippet, depth)
  │      · detect_trigger(text, qtype, difficulty, policy_terms)  ← 경량 트리거 판정(휴리스틱 대체)
  │
  └─ 채점 ─────────────── AnthropicScorerClient  (scorer.LLMClient 인터페이스 구현)
         · score(question, answer, rubric, written_task, prev_answers, region_context, question_type)

설계 원천(프롬프트·스키마 그대로 계승):
  - data/08-system/면접관-페르소나-세트.md      §1(페르소나 시스템 프롬프트)·§3(트리거 매핑)·§5(하드 가드레일)
  - data/08-system/채점-프롬프트-실장.md        §1(채점 System/User + JSON 스키마)·§3(red flag 탐지)
  - data/06-answer-guides/질문생성-프롬프트-템플릿.md  §4(꼬리질문 방향)

역할별 모델 선택(★ 정확한 모델 ID) — 이유는 각 상수 옆 주석 참고:
  - 면접관 대화     = claude-sonnet-5
  - 트리거/경량판정 = claude-haiku-4-5-20251001
  - 채점 앙상블     = claude-opus-4-8

운영 특성:
  - 프롬프트 캐싱: system 블록 프리픽스(가드레일+컨텍스트 / 루브릭+few-shot)에 cache_control 부착.
  - API 키는 환경변수 ANTHROPIC_API_KEY 에서 로드. 키가 없으면 '실제 호출' 시점에 명확한 에러.
  - anthropic 패키지 미설치 시에도 import·인스턴스화·프롬프트 조립·드라이런은 정상 동작한다.
  - 드라이런(dry_run=True): 실제 API 호출 대신 '조립된 프롬프트(모델·파라미터·system·user)'를 출력/반환.

주의(현행 모델 API 제약, claude-api 스킬 반영):
  - claude-sonnet-5 / claude-opus-4-8 은 temperature/top_p/top_k 를 받지 않는다(400).
    → 설계 문서의 "채점 temp 0.0~0.2 / 꼬리질문 temp 0.3" 권장은 이 모델들에선 프롬프트 지시로 대체한다.
    → temperature 는 sampling 파라미터를 허용하는 claude-haiku-4-5-20251001(경량 판정)에만 적용한다.
  - thinking: enabled+budget_tokens 는 4.7+/Sonnet5/Opus4.8 에서 제거됨. adaptive/disabled 만 사용.
"""

import argparse
import json
import os
import re

# ---------------------------------------------------------------------------
# anthropic SDK — 미설치여도 import/조립/드라이런은 되도록 try/except 로 감싼다.
# ---------------------------------------------------------------------------
try:
    import anthropic  # type: ignore
    _ANTHROPIC_AVAILABLE = True
    _ANTHROPIC_IMPORT_ERROR = None
except Exception as _e:  # ImportError 외 환경 문제 포함
    anthropic = None  # type: ignore
    _ANTHROPIC_AVAILABLE = False
    _ANTHROPIC_IMPORT_ERROR = _e


# ===========================================================================
# 0. 역할별 모델 ID (정확 문자열 — 날짜 접미사 임의 부착 금지)
# ===========================================================================
# 면접관 대화: 수십 턴의 짧은 페르소나 발화를 낮은 지연/비용으로 자연스럽게. 옵셔스급 품질에 근접.
MODEL_INTERVIEWER = "claude-sonnet-5"
# 트리거/경량 판정: 답변당 1회 도는 이진 트리거 탐지 — 깊은 추론보다 속도·저비용이 우선.
MODEL_LIGHTWEIGHT = "claude-haiku-4-5-20251001"
# 채점 앙상블: 합격/미흡을 가르는 임계 판정. reasoning→verdict 에 최상위 판단력이 필요하고,
#              답변당 위원 N회 호출되므로 판정 품질이 가장 중요 → 최상위 Opus.
MODEL_SCORER = "claude-opus-4-8"

# sampling 파라미터(temperature 등)를 허용하는 모델만 온도를 넣는다.
_SAMPLING_OK = {MODEL_LIGHTWEIGHT}


# ===========================================================================
# 1. 프롬프트 상수 (문서 §를 그대로 옮긴 것)
# ===========================================================================

# --- 면접관-페르소나-세트.md §5 하드 가드레일 (전 페르소나 공통·상위 우선) ----------
GUARDRAILS = """[하드 가드레일 — 전 페르소나 공통, 상위 우선]
1. 블라인드 유지: 나이·학력·출신지·성별·가족사항·결혼/출산 여부·재산·종교·정치성향을
   묻거나 추정하는 질문을 절대 하지 않는다. 응시자가 스스로 연고지 등을 언급해도 그것을
   근거로 한 질문을 만들지 않는다.
2. 차별 질문 금지: 직무와 무관한 장애·신체·질병, 결혼·출산 계획, 정치적 지지 정당, 종교
   신념, 성역할 고정관념에 기댄 질문 금지.
3. 인신공격·모욕 금지: 외모·말투·목소리·인격·배경 비하 금지. 압박형이라도 "틀렸다"는
   단정적 모욕·윽박·비아냥 금지. 검증은 판단 근거를 되묻는 방식으로만.
4. 자기붕괴 유도 금지: 실수·침묵을 조롱하거나 자기붕괴를 유발하지 않는다. 오답 후 회복
   기회를 준다. 단발성 실수·버벅임은 미흡 사유가 아니다.
5. 사실 날조 금지: 주입된 [지자체 컨텍스트]·[직렬 컨텍스트]에 없는 정책명·사업명·수치를
   지어내지 않는다. 지역질문은 자료에 있는 사실만 소재로 쓴다.
6. 질문 형식: 한 번에 하나, 2문장 이내. 복합 질문 금지. 9급 신규 수준을 넘는 세부 조문
   암기 요구 금지.
위 규칙과 페르소나 지시가 충돌하면 언제나 위 규칙이 우선한다."""

# --- 면접관-페르소나-세트.md §1-1/1-2/1-3 페르소나 시스템 프롬프트 본문 -----------
# {임용기관}/{직급} 슬롯은 런타임에 region/job 으로 치환.
INTERVIEWER_PERSONA = {
    "온화형": """[페르소나: 위원A / 온화형]
당신은 대한민국 {임용기관} {직급} 공무원 면접시험의 면접위원 '위원A'다.
당신의 역할은 인성·경험·공직동기를 확인하고, 응시자의 긴장을 완화해 진솔한 답변을
끌어내는 것이다.
말투: 항상 존댓말. 부드럽고 따뜻한 어조. 안심시키는 표현을 앞에 둔다("편하게 말씀하세요").
      공감 리액션을 붙이되("그러셨군요") 과장된 칭찬으로 평가를 오도하지 않는다.
행동 규칙:
- 질문은 한 번에 하나, 2문장 이내. 열린 질문·경험 회고형 위주. 답변을 끊지 않는다.
- 침묵/얼면 압박하지 않고 잠시 기다린 뒤 소재 힌트를 하나 준다.
- 경험 주장(T3)엔 STAR 중 빠진 단계 하나만 부드럽게 되묻는다(역할→행동→결과→배운 점).
- 추상어·선언(T4)엔 비난 없이 "구체적으로 어떤 방법으로?"처럼 구체화를 청한다.
- 자기붕괴 발화가 나와도 "괜찮습니다, 이어서 해볼까요?"로 회복 기회를 준다.
- red flag·모순 추궁·조건 변경 압박은 하지 않는다(위원C 담당).""",
    "표준형": """[페르소나: 위원B / 표준형]
당신은 대한민국 {임용기관} {직급} 공무원 면접시험의 면접위원 '위원B'다.
당신의 역할은 직무지식·지역현안·정책이해를 중립적이고 체계적으로 검증하는 것이다.
말투: 존댓말, 사무적이고 간결한 어조. 감정 표현 절제. 칭찬도 질책도 하지 않는다.
      질문 전 짧은 전환 신호를 준다("그럼 직무 관련해서 여쭙겠습니다").
행동 규칙:
- 질문은 한 번에 하나, 2문장 이내. 복합 질문 금지.
- 지역현안은 [지자체 컨텍스트] 자료에 있는 정책·현안만 소재로 쓴다.
- 정책·수치 언급(T5)엔 한계·보완점을 되묻거나 자료와 대조해 오류 시 정정 기회형으로 확인.
- 9급 신규 수준을 넘는 세부 조문 번호·시행령 세칙 암기는 묻지 않는다.
- 사실관계가 부정확해도 즉시 감점 발화를 하지 않고 정정 기회를 1회 준다.
- 인성·동기 격려(위원A)나 조건변경 압박(위원C)으로 넘어가지 않는다.""",
    "압박형": """[페르소나: 위원C / 압박형]
당신은 대한민국 {임용기관} {직급} 공무원 면접시험의 면접위원 '위원C'다.
당신의 역할은 답변의 진실성·일관성·공직가치를 정중하지만 집요하게 검증하는 것이다.
말투: 존댓말. 차분하고 절제된 어조를 유지하되 물러서지 않는다. 목소리를 높이거나
      비아냥대지 않는다. 응시자가 실제로 쓴 표현을 인용해 되받는다("방금 ~라고 하셨는데").
행동 규칙:
- 질문은 한 번에 하나, 1~2문장. 검증 목적이 드러나는 후속질문 형태.
- red flag(T1)엔 비난하지 않고 소명 기회를 1회 준다("그렇게 판단하신 근거는 무엇입니까?").
- 진술 모순(T2)은 두 진술을 나란히 인용하고 어느 쪽인지 묻는다.
- 원칙답변(T6)엔 조건을 하나 바꿔 원칙이 흔들리는 지점을 만든다.
- 마지막 뎁스에 도달하면 마무리형(판단 확인)으로 묻고 종료한다.
- 절대 하지 않는다: 인신공격, 외모·배경·인격 비하, "틀렸다"는 단정적 모욕, 답 강요.""",
}

_INTERVIEWER_OUTPUT_RULE = (
    "[출력 규칙] 면접관 한 사람의 발화 문장만 한국어 존댓말로 출력한다. "
    "따옴표·역할표기(위원A: 등)·메타설명·JSON·마크다운을 붙이지 않는다."
)

# 트리거 상수(면접관-페르소나-세트.md §3 / 세션-설계.md §2-2) — 자체 보유(순환 import 회피)
TRIGGER_NAME = {
    "T1": "red flag(소명)", "T2": "진술모순", "T3": "경험주장(STAR)",
    "T4": "추상어(구체화)", "T5": "정책·수치(지식검증)", "T6": "원칙답변(조건변경)",
    "T7": "미완결(유도재질문)",
}
TRIGGER_MAXDEPTH = {"T1": 1, "T2": 2, "T3": 3, "T4": 2, "T5": 2, "T6": 3, "T7": 1}
TRIGGER_DIRECTION = {
    "T1": "비난 없이 판단 근거를 되묻는 소명 기회 1회.",
    "T2": "두 진술을 나란히 인용하고 어느 쪽이 맞는지 묻는다.",
    "T3": "STAR 중 답변에 빠진 단계 하나만 부드럽게 파고든다(역할→행동→결과→배운 점).",
    "T4": "선언을 실행 방법·사례로 구체화하게 한다.",
    "T5": "언급한 정책의 한계·보완점 또는 정확한 이해를 확인한다(자료 대조, 오류 시 정정 기회형).",
    "T6": "조건을 하나 바꿔 원칙이 흔들리는 지점을 만든다(압박이되 정중하게).",
    "T7": "유도 재질문(압박 아님). 사례를 예시로 들어 다시 청한다.",
}

# --- 채점-프롬프트-실장.md §1-1 System (루브릭 전문 + red flag; few-shot/페르소나는 뒤에 부착) --
SCORER_SYSTEM_RUBRIC = """당신은 대한민국 공무원 면접시험의 평가위원이다. 아래 [루브릭]과 [few-shot 앵커]에
따라 응시자의 단일 답변을 4대 평정요소별로 상/중/하로 평정한다.

[절대 원칙]
1. 판정 전에 반드시 근거를 먼저 서술하고, 그다음에 판정한다(reasoning → verdict).
2. 모든 요소 판정에는 답변 원문에서 그대로 따온 직접 인용을 1개 이상 첨부한다.
   원문에 없는 내용을 근거로 삼지 않는다(환각 채점 금지).
3. 미흡(하)은 결격 신호로만 준다. 버벅임·짧은 침묵(2~3초)·단발 오답·긴장·유창성
   부족·짧은 답변은 그 자체로 '하' 사유가 아니다. 확신이 없으면 '중'을 준다.
4. 비언어(표정·시선)나 필기점수·스펙 등 답변 외 정보는 평정에 반영하지 않는다.
5. 자료([지역 컨텍스트])에 없는 사실의 정오는 판정하지 않는다. 모른다고 표시한다.
6. 출력은 지정된 JSON 스키마만. 스키마 밖 텍스트·설명·마크다운을 출력하지 않는다.

[4대 평정요소와 상/중/하 기준]
① 소통·공감: 두괄식·질문의도 부합·상대(민원인/동료/상사) 관점 언급·경청/협업.
   상 = 결론 선행 + 질문의도 정확 부합 + 상대 관점 1회+ 구체 언급 + 협의/경청 포함
   중 = 질문에 부합하나 상대 관점이 형식적이거나 구조가 산만
   하 = 동문서답 / 준비답변 낭독 / 자기 관점만 / 문장 미완결 / 상대 비하
② 헌신·열정: 공직동기 구체성·적극성·직무/기관 이해·완수 서사.
   상 = 경험 근거의 동기 + 자발 행동("먼저/제가 나서서") + 완수/극복 서사
   중 = 방향은 맞으나 선언적이고 준비 행동·경험 근거 부재
   하 = 공직동기 결여("안정적이라서" 단독) / 직무 지속 유보 / 부정적·냉소적 공직관
③ 창의·혁신: 대안 독자성·전략적 사고(원인→우선순위→단계)·근거 기반·실현가능성.
   상 = 현행 인지 + 보완 제안 + 근거(수치/사례) 1개+ + 단계적 실행
   중 = 나열식, 원인분석·구체 근거 부재, 통념 수준
   하 = 분석·대안 전무 / 비현실적 공약 / 변화 거부·냉소
④ 윤리·책임: 법규·공익 우선·책임 귀속·공정성·청렴·일관성.
   상 = 법령/공익을 판단기준으로 명시 + 책임 인정 + 절차(보고/협의) 준수 + 상대 배려
   중 = 원칙은 지키나 근거가 빈약하거나 기계적
   하 = 규정 무시/사익 우선/책임 전가/은폐/금품 애매 수용/진술 모순·거짓 (→ red flag)

[red flag — 탐지 시 해당 요소 무조건 '하']
- 반공직·냉소적 공직관("봉사정신으로 공무원 하나", "월급 받는 직장일 뿐")
- 위법·비윤리 행동의 정당화("규정 어겨도 따르겠다", "융통성 있게 받아도")
- 타인/국민 비하·협업 거부("진상", "상대 안 함", "게을러서 대화 안 통함")
- 은폐·책임 전가("조용히 넘어간다", "내 책임 아니다", "모른 척한다")
- 진술 모순·거짓 정황([사전 과제]·[이전 답변]과 해소 불가한 모순)
- 지속적 침묵·답변 포기·자기붕괴, 실질 내용 없는 답변·동문서답
  ※ 단, "정확히는 모르지만 ~로 이해하며 임용 전 확인하겠다" 류 회복 시도는 red flag 아님."""

# --- 채점-프롬프트-실장.md §1-3 위원 페르소나 (기질만 다름, 루브릭 공유·덮어쓰기 금지) ------
SCORER_PERSONA = {
    "J-STD": """[위원 페르소나]
# 표준위원(J-STD) — 기준값
평정 기준을 문자 그대로 적용한다. 상과 하 어느 쪽으로도 치우치지 않으며, 확신이 없으면
'중'을 준다. 미흡 보수 판정 원칙을 그대로 지킨다.""",
    "J-STR": """[위원 페르소나]
# 엄격위원(J-STR) — red flag 민감
윤리·책임과 일관성을 특히 예민하게 본다. red flag 신호(위법 정당화·은폐·모순·반공직
발화)를 놓치지 않는다. 단, 유창성 부족·긴장·짧은 답변으로는 절대 감점하지 않는다.""",
    "J-JOB": """[위원 페르소나]
# 직무위원(J-JOB) — 직무·현안 정확성 중시
창의·혁신과 헌신·열정에서 직무/기관 이해도·현안 지식의 정확성을 특히 본다. 단 9급 신규
수준을 넘는 세부 조문 암기 부재는 감점하지 않는다. 지역현안 사실 정오는 [지역 컨텍스트]
자료 범위 안에서만 판단하고, 자료 밖은 '판단 보류'로 둔다.""",
}

# --- 채점-프롬프트-실장.md §1-2 User 프롬프트 템플릿 --------------------------------
SCORER_USER_TEMPLATE = """[채점 대상]
질문유형: {question_type}
질문: {question}
답변(전사문): {answer}
사전 과제 요약: {written_task}
이전 답변 요약: {prev_answers}
지역 컨텍스트(사실 근거): {region_context}

위 답변을 4대 평정요소별로 평정하라. 각 요소마다 (1) 근거를 먼저 서술하고
(2) 답변 원문 인용을 붙인 뒤 (3) 상/중/하를 판정한다. red flag를 별도로 수집하고,
스피치·비언어는 판정에 넣지 말고 speech_note에 코칭용으로만 분리 기록하라.
아래 JSON 스키마로만 출력한다."""

# --- 채점-프롬프트-실장.md §1-4 JSON 출력 스키마 (structured outputs 용) ----------------
_VERDICT = {"type": "string", "enum": ["상", "중", "하"]}
_ELEMENT_OBJ = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "verdict": _VERDICT,
    },
    "required": ["reasoning", "evidence", "verdict"],
    "additionalProperties": False,
}
SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "committee_id": {"type": "string", "enum": ["J-STD", "J-STR", "J-JOB"]},
        "elements": {
            "type": "object",
            "properties": {
                "소통공감": _ELEMENT_OBJ, "헌신열정": _ELEMENT_OBJ,
                "창의혁신": _ELEMENT_OBJ, "윤리책임": _ELEMENT_OBJ,
            },
            "required": ["소통공감", "헌신열정", "창의혁신", "윤리책임"],
            "additionalProperties": False,
        },
        "red_flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"}, "element": {"type": "string"},
                    "quote": {"type": "string"}, "note": {"type": "string"},
                },
                "required": ["type", "element", "quote", "note"],
                "additionalProperties": False,
            },
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
        "improvements": {"type": "array", "items": {"type": "string"}},
        "model_answer_direction": {"type": "string"},
        "speech_note": {"type": "string"},
        "member_grade": {"type": "string", "enum": ["우수", "보통", "미흡"]},
    },
    "required": [
        "committee_id", "elements", "red_flags", "strengths", "improvements",
        "model_answer_direction", "speech_note", "member_grade",
    ],
    "additionalProperties": False,
}

# --- 채점-프롬프트-실장.md §3 red flag 탐지(경량 판정, Haiku) System/스키마 --------------
REDFLAG_SYSTEM = """당신은 공무원 면접 답변에서 '결격 트리거(red flag)'만 탐지하는 판정기다. 품질·등급을
매기지 않는다. 아래 트리거 중 명백히 발화된 것만 보고한다.
① 반공직가치관 ② 타인비하·비협조 ③ 침묵·답변포기 ④ 자기붕괴 ⑤ 일관성붕괴·거짓
(파생) 위법정당화 / 은폐·책임전가
[보수 판정 규칙 — 오탐 억제]
- 버벅임·짧은 침묵·단발 오답·긴장·유창성 부족은 트리거가 아니다.
- "정확히는 모르지만 ~로 이해하며 임용 전 확인하겠다"류 회복 시도는 트리거 아님.
- ⑤는 [사전 과제]/[이전 답변]이 입력에 있을 때만 판정 가능. 없으면 판정 보류.
- 확신 없으면 트리거를 잡지 않는다(false 우선). confidence 0.7 미만은 fired=false.
출력은 지정 JSON 스키마만."""

REDFLAG_SCHEMA = {
    "type": "object",
    "properties": {
        "has_red_flag": {"type": "boolean"},
        "triggers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "element": {"type": "string"},
                    "quote": {"type": "string"},
                    "confidence": {"type": "number"},
                    "fired": {"type": "boolean"},
                    "rationale": {"type": "string"},
                },
                "required": ["type", "element", "quote", "confidence", "fired", "rationale"],
                "additionalProperties": False,
            },
        },
        "borderline_notes": {"type": "string"},
    },
    "required": ["has_red_flag", "triggers", "borderline_notes"],
    "additionalProperties": False,
}


# ===========================================================================
# 2. 공통 유틸 (SDK 로딩 / JSON 추출 / 컨텍스트 조립 / 드라이런 렌더)
# ===========================================================================
def _require_sdk_and_key(api_key):
    """실제 호출 직전 검증. 미설치/키없음이면 명확한 한국어 에러."""
    if not _ANTHROPIC_AVAILABLE:
        raise RuntimeError(
            "anthropic 패키지가 설치되어 있지 않습니다. `pip install anthropic` 후 사용하세요. "
            "(원인: %r) — 드라이런은 패키지 없이도 동작합니다: dry_run=True / --dry-run"
            % (_ANTHROPIC_IMPORT_ERROR,)
        )
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "환경변수 ANTHROPIC_API_KEY 가 설정되어 있지 않습니다. 실제 호출에는 API 키가 필요합니다. "
            "(export ANTHROPIC_API_KEY=...) — 드라이런은 키 없이 동작합니다: dry_run=True / --dry-run"
        )
    return key


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(text):
    """LLM 텍스트에서 JSON 오브젝트를 견고하게 추출. 코드펜스/선행텍스트 허용."""
    if not text:
        raise ValueError("빈 응답 — JSON 없음")
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1)
    text = text.strip()
    # 첫 '{' ~ 마지막 '}' 슬라이스로 방어적 추출
    if not text.startswith("{"):
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e != -1 and e > s:
            text = text[s:e + 1]
    return json.loads(text)


def _first_text(resp):
    """messages.create 응답 content 에서 첫 text 블록 문자열."""
    parts = []
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def _context_block(ctx):
    """세션 컨텍스트 dict → [지자체 컨텍스트]/[직렬 컨텍스트] 텍스트 블록(자료에 있는 것만)."""
    ctx = ctx or {}
    lines = ["[지자체 컨텍스트]", "- 지자체: %s" % ctx.get("region", "(미상)")]
    slogan = ctx.get("슬로건") or ""
    vision = ctx.get("시정비전") or ""
    if slogan:
        lines.append("- 슬로건: %s" % slogan)
    if vision:
        lines.append("- 시정비전: %s" % (vision[:120]))
    issues = ctx.get("지역현안") or []
    if issues:
        lines.append("- 지역현안: %s" % "; ".join(str(x) for x in issues[:5]))
    biz = ctx.get("핵심사업") or []
    if biz:
        lines.append("- 핵심사업: %s" % "; ".join(str(x) for x in biz[:5]))
    lines.append("")
    lines.append("[직렬 컨텍스트]")
    lines.append("- 직렬: %s" % ctx.get("job", "(미상)"))
    duty = ctx.get("주요업무") or []
    if duty:
        lines.append("- 주요업무: %s" % "; ".join(str(x) for x in duty[:5]))
    inst = ctx.get("핵심제도") or []
    if inst:
        lines.append("- 핵심제도: %s" % "; ".join(str(x) for x in inst[:5]))
    lines.append("")
    lines.append("위 자료에 없는 정책명·수치를 지어내지 않는다(§5-5).")
    return "\n".join(lines)


def _fill(persona_text, ctx):
    ctx = ctx or {}
    return (persona_text
            .replace("{임용기관}", str(ctx.get("region", "해당 지자체")))
            .replace("{직급}", str(ctx.get("job", "해당 직렬"))))


def render_request(req):
    """조립된 요청(dict)을 사람이 읽을 수 있는 드라이런 텍스트로 렌더."""
    out = []
    out.append("=" * 78)
    out.append("[DRY-RUN] 실제 호출 대신 조립된 프롬프트를 출력합니다.")
    out.append("model      : %s" % req["model"])
    out.append("max_tokens : %s" % req["max_tokens"])
    params = {k: v for k, v in req.get("params", {}).items()}
    out.append("params     : %s" % json.dumps(params, ensure_ascii=False))
    out.append("-" * 78)
    for i, blk in enumerate(req["system"]):
        cc = " (cache_control=ephemeral)" if blk.get("cache_control") else ""
        out.append("[system #%d]%s" % (i, cc))
        out.append(blk["text"])
        out.append("")
    out.append("-" * 78)
    for msg in req["messages"]:
        out.append("[%s]" % msg["role"])
        content = msg["content"]
        if isinstance(content, str):
            out.append(content)
        else:
            out.append(json.dumps(content, ensure_ascii=False, indent=2))
        out.append("")
    out.append("=" * 78)
    return "\n".join(out)


# ===========================================================================
# 3. 면접관 클라이언트 (session_engine.LLMClient 프로토콜 구현)
# ===========================================================================
class AnthropicInterviewerClient:
    """
    실제 Claude 면접관. session_engine.MockLLMClient 를 이 클래스로 교체하면 규칙 템플릿
    대신 실제 페르소나 발화를 생성한다(세션 엔진 코드 무수정).

    - 발화(interviewer_turn): claude-sonnet-5, thinking disabled(짧은 발화라 추론 불필요).
    - 트리거 판정(detect_trigger): claude-haiku-4-5-20251001, temperature 0.0(경량·저비용).
    프롬프트 캐싱: system[0] = 가드레일+컨텍스트(세션 내 동결) 프리픽스에 cache_control.
    """

    def __init__(self, api_key=None, dry_run=False, followup_temperature=0.3):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.dry_run = dry_run
        # 설계 권장 꼬리질문 온도(0.3)는 sonnet-5 에서 무시(파라미터 미허용) → 참고용 보관.
        self.followup_temperature = followup_temperature
        self._client_obj = None

    def _client(self):
        if self._client_obj is None:
            key = _require_sdk_and_key(self.api_key)
            self._client_obj = anthropic.Anthropic(api_key=key)
        return self._client_obj

    # ---- 프롬프트 조립 (공개: 드라이런/테스트에서 직접 호출 가능) --------------------
    def build_turn(self, kind, *, persona=None, context=None, question=None,
                   answer=None, trigger=None, snippet=None, depth=0):
        persona = persona or "표준형"  # 진행(intro/wrapup 등)은 표준형(위원B)이 담당
        persona_text = _fill(INTERVIEWER_PERSONA.get(persona, INTERVIEWER_PERSONA["표준형"]),
                             context)
        system = [
            {   # 프리픽스(세션 동결) — 캐시 대상: 가드레일 + 지자체/직렬 컨텍스트
                "type": "text",
                "text": GUARDRAILS + "\n\n" + _context_block(context),
                "cache_control": {"type": "ephemeral"},
            },
            {   # 페르소나(턴별 3종) + 출력 규칙 — 프리픽스 뒤(캐시 경계 밖)
                "type": "text",
                "text": persona_text + "\n\n" + _INTERVIEWER_OUTPUT_RULE,
            },
        ]
        user = self._turn_user(kind, context, question, answer, trigger, snippet, depth)
        # sonnet-5: temperature 미허용 → 넣지 않는다. 짧은 발화라 thinking 비활성.
        return {
            "model": MODEL_INTERVIEWER,
            "max_tokens": 512,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "params": {"thinking": {"type": "disabled"}},
        }

    def _turn_user(self, kind, ctx, q, answer, trigger, snippet, depth):
        ctx = ctx or {}
        if kind == "intro":
            return ("세션 오프닝 안내를 하라. 환영 인사 + 트랙(%s)·난이도(%s)·참여위원(%s) 안내 + "
                    "제도는 응시 연도 공고문 확인 필요 고지를, 진행자(위원B) 어조로 2~3문장으로."
                    % (ctx.get("track", ""), ctx.get("difficulty", ""),
                       ", ".join(ctx.get("personas", []))))
        if kind == "speech_prompt":
            sec = ctx.get("speech_sec") or 300
            return ("스피치 제시문을 제시하라. [지자체 컨텍스트]의 지역현안 1건을 소재로, "
                    "%d분 내외 발표를 안내하는 1~2문장." % (sec // 60))
        if kind == "speech_ack":
            return "응시자 발표를 잘 들었다는 짧고 중립적인 반응 1문장을 발화하라."
        if kind == "main":
            q = q or {}
            return ("다음 주질문을 당신(페르소나) 어조로 발화하라(한 번에 하나, 2문장 이내). "
                    "질문유형=%s, 질문원문=%s. 지역현안 유형이면 [지자체 컨텍스트]의 현안 한 문장을 "
                    "앞에 얹어도 좋다(자료 밖 사실 금지)."
                    % (q.get("type", ""), (q.get("text") or "").strip()))
        if kind == "followup":
            name = TRIGGER_NAME.get(trigger, trigger or "")
            maxd = TRIGGER_MAXDEPTH.get(trigger, 1)
            direction = TRIGGER_DIRECTION.get(trigger, "답변을 구체화하도록 되묻는다.")
            closing = " 현재가 마지막 뎁스이므로 마무리형(판단 확인)으로 묻는다." if depth >= maxd else ""
            return ("응시자 답변에 트리거 %s(%s)가 감지되었다. 감지 표현: '%s'.\n"
                    "직전 답변 전사문: %s\n"
                    "방식: %s 답변에 실제 등장한 표현을 1개 이상 인용해 꼬리질문 1개(1~2문장)를 "
                    "생성하라. 현재 뎁스 %d/%d.%s"
                    % (trigger, name, snippet or "", (answer or "").strip(),
                       direction, depth, maxd, closing))
        if kind == "wrapup":
            return "마지막으로 하고 싶은 말을 청하는 1문장을 발화하라."
        if kind == "closing":
            return "면접 종료·감사 멘트 1문장을 발화하라."
        return "면접 진행에 필요한 짧은 발화 1문장을 하라."

    # ---- LLMClient 프로토콜 ------------------------------------------------
    def interviewer_turn(self, kind, *, persona=None, context=None, question=None,
                         answer=None, trigger=None, snippet=None, depth=0):
        req = self.build_turn(kind, persona=persona, context=context, question=question,
                              answer=answer, trigger=trigger, snippet=snippet, depth=depth)
        if self.dry_run:
            return render_request(req)  # 조립된 프롬프트 문자열 반환
        resp = self._client().messages.create(
            model=req["model"], max_tokens=req["max_tokens"],
            system=req["system"], messages=req["messages"], **req["params"],
        )
        return _first_text(resp)

    # ---- 경량 트리거 판정 (Haiku) — 세션 엔진의 키워드 휴리스틱 대체 ----------------
    def build_trigger(self, text, qtype=None, difficulty="실전",
                      written_task=None, prev_answers=None):
        allowed = "T1(red flag)·T7(미완결)만" if difficulty == "초급" else "T1~T7"
        user = ("질문유형: %s\n답변(전사문): %s\n사전 과제 요약: %s\n이전 답변 요약: %s\n\n"
                "위 답변에서 꼬리질문 트리거를 탐지하라. 허용 트리거: %s. 우선순위(T1>T2>…>T7)로 "
                "'가장 우선하는 트리거 1개'만 고른다. 없으면 trigger=null. 원문에서 감지 근거가 된 "
                "표현(snippet)을 인용하라. 확신 없으면 null(보수적)."
                % (qtype or "", (text or "").strip(), written_task or "null",
                   prev_answers or "null", allowed))
        schema = {
            "type": "object",
            "properties": {
                "trigger": {"type": ["string", "null"],
                            "enum": ["T1", "T2", "T3", "T4", "T5", "T6", "T7", None]},
                "snippet": {"type": ["string", "null"]},
                "confidence": {"type": "number"},
                "rationale": {"type": "string"},
            },
            "required": ["trigger", "snippet", "confidence", "rationale"],
            "additionalProperties": False,
        }
        system = [{
            "type": "text",
            "text": ("당신은 공무원 면접 답변에서 꼬리질문 트리거만 판정하는 경량 판정기다. "
                     "T1 red flag / T2 진술모순 / T3 경험주장 / T4 추상어·선언 / "
                     "T5 정책·수치 언급 / T6 상황형 원칙답변 / T7 미완결. "
                     "버벅임·긴장·짧은 답변은 트리거가 아니다. 출력은 지정 JSON 스키마만."),
            "cache_control": {"type": "ephemeral"},
        }]
        # Haiku 4.5 는 sampling 허용 → 결정성을 위해 temperature 0.0.
        return {
            "model": MODEL_LIGHTWEIGHT,
            "max_tokens": 400,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "params": {"temperature": 0.0,
                       "output_config": {"format": {"type": "json_schema", "schema": schema}}},
        }

    def detect_trigger(self, text, qtype=None, difficulty="실전",
                       written_task=None, prev_answers=None, policy_terms=None):
        """반환: (trigger_id 또는 None, snippet 또는 None). session_engine.detect_trigger 시그니처 호환."""
        req = self.build_trigger(text, qtype=qtype, difficulty=difficulty,
                                 written_task=written_task, prev_answers=prev_answers)
        if self.dry_run:
            print(render_request(req))
            return None, None
        # Haiku 는 output_config 미지원 가능성 방어: 실패 시 JSON 지시로 폴백.
        params = dict(req["params"])
        try:
            resp = self._client().messages.create(
                model=req["model"], max_tokens=req["max_tokens"],
                system=req["system"], messages=req["messages"], **params)
        except Exception:
            params.pop("output_config", None)
            resp = self._client().messages.create(
                model=req["model"], max_tokens=req["max_tokens"],
                system=req["system"], messages=req["messages"], **params)
        data = _extract_json(_first_text(resp))
        trig = data.get("trigger")
        if trig and float(data.get("confidence", 0)) >= 0.7:
            return trig, data.get("snippet")
        return None, None


# ===========================================================================
# 4. 채점 클라이언트 (scorer.LLMClient 인터페이스 구현)
# ===========================================================================
class AnthropicScorerClient:
    """
    실제 Claude 채점위원 1인. scorer.MockScorer 를 이 클래스로 교체하면 규칙 근사 대신 §1
    프롬프트로 LLM 채점을 수행한다(scorer 코드 무수정 — score_answer(..., client=) 에 주입).

    - 채점(score): claude-opus-4-8, adaptive thinking(reasoning→verdict 품질), structured
      outputs(§1-4 스키마 강제). temperature 미허용 모델이라 결정성은 프롬프트로 유도.
    - red flag 2차 판정(detect_red_flags): claude-haiku-4-5-20251001(경량·저비용, §3 프롬프트).
    프롬프트 캐싱: system[0] = 루브릭 전문 + few-shot(세션 동결) 프리픽스에 cache_control,
                  system[1] = 위원 페르소나(N회 호출 시 이 블록만 교체).
    """

    def __init__(self, committee_id="J-STD", api_key=None, dry_run=False, fewshot_block=""):
        if committee_id not in SCORER_PERSONA:
            raise ValueError("알 수 없는 committee_id: %s (허용: J-STD/J-STR/J-JOB)" % committee_id)
        self.committee_id = committee_id
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.dry_run = dry_run
        self.fewshot_block = fewshot_block or "(few-shot 앵커 미주입 — §5 조립 가이드로 채운다)"
        self._client_obj = None

    def _client(self):
        if self._client_obj is None:
            key = _require_sdk_and_key(self.api_key)
            self._client_obj = anthropic.Anthropic(api_key=key)
        return self._client_obj

    def build_score(self, question, answer, rubric=None, written_task=None,
                    prev_answers=None, region_context=None, question_type=None):
        prefix = (SCORER_SYSTEM_RUBRIC
                  + "\n\n[few-shot 앵커]\n" + self.fewshot_block)
        system = [
            {"type": "text", "text": prefix, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": SCORER_PERSONA[self.committee_id]},
        ]
        user = SCORER_USER_TEMPLATE.format(
            question_type=question_type or "(미상)",
            question=(question or "").strip(),
            answer=(answer or "").strip(),
            written_task=written_task if written_task else "null",
            prev_answers=prev_answers if prev_answers else "null",
            region_context=region_context if region_context else "null",
        )
        # opus-4-8: temperature 미허용. adaptive thinking + structured outputs.
        return {
            "model": MODEL_SCORER,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "params": {
                "thinking": {"type": "adaptive"},
                "output_config": {"format": {"type": "json_schema", "schema": SCORE_SCHEMA}},
            },
        }

    def score(self, question, answer, rubric=None, written_task=None,
              prev_answers=None, region_context=None, question_type=None):
        req = self.build_score(question, answer, rubric=rubric, written_task=written_task,
                               prev_answers=prev_answers, region_context=region_context,
                               question_type=question_type)
        if self.dry_run:
            # 채점 결과 스키마 대신 조립 프롬프트를 담아 반환(집계에는 투입하지 않음).
            return {"_dry_run": True, "committee_id": self.committee_id,
                    "_prompt": render_request(req)}
        resp = self._client().messages.create(
            model=req["model"], max_tokens=req["max_tokens"],
            system=req["system"], messages=req["messages"], **req["params"])
        data = _extract_json(_first_text(resp))
        data.setdefault("committee_id", self.committee_id)
        return data

    # ---- red flag 2차 판정 (Haiku, §3) ------------------------------------
    def build_red_flags(self, question, answer, written_task=None, prev_answers=None):
        user = ("질문: %s\n답변(전사문): %s\n사전 과제 요약: %s\n이전 답변 요약: %s\n\n"
                "위 답변에서 결격 트리거를 탐지하라. 트리거가 없으면 triggers는 빈 배열이다. "
                "반드시 원문 인용을 근거로 제시하고, confidence 0.7 미만은 fired=false로 둔다."
                % ((question or "").strip(), (answer or "").strip(),
                   written_task or "null", prev_answers or "null"))
        system = [{"type": "text", "text": REDFLAG_SYSTEM,
                   "cache_control": {"type": "ephemeral"}}]
        return {
            "model": MODEL_LIGHTWEIGHT,
            "max_tokens": 800,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "params": {"temperature": 0.0,
                       "output_config": {"format": {"type": "json_schema", "schema": REDFLAG_SCHEMA}}},
        }

    def detect_red_flags(self, question, answer, written_task=None, prev_answers=None):
        req = self.build_red_flags(question, answer, written_task=written_task,
                                   prev_answers=prev_answers)
        if self.dry_run:
            return {"_dry_run": True, "_prompt": render_request(req)}
        params = dict(req["params"])
        try:
            resp = self._client().messages.create(
                model=req["model"], max_tokens=req["max_tokens"],
                system=req["system"], messages=req["messages"], **params)
        except Exception:
            params.pop("output_config", None)
            resp = self._client().messages.create(
                model=req["model"], max_tokens=req["max_tokens"],
                system=req["system"], messages=req["messages"], **params)
        return _extract_json(_first_text(resp))


# ===========================================================================
# 5. 드라이런 데모
# ===========================================================================
def _demo_context():
    """session_engine.SessionEngine 이 만드는 ctx 와 같은 형태의 샘플."""
    return {
        "region": "대구광역시", "job": "일반행정직",
        "track": "지방직표준", "difficulty": "실전",
        "personas": ["온화형", "표준형", "압박형"],
        "speech_sec": 0,
        "시정비전": "새로운 대구, 미래로 도약",
        "슬로건": "파워풀 대구",
        "지역현안": ["청년 유출(청년 감소율 20.5%)", "동성로 르네상스 프로젝트(2023~2028, 4개 분야 13개 사업)"],
        "핵심사업": ["5대 미래 신산업 육성", "군위군 편입·대구경북통합신공항"],
        "주요업무": ["민원 처리·행정 지원", "예산·서무", "지역 정책 집행"],
        "핵심제도": ["적극행정·적극행정 면책", "공무원 행동강령"],
    }


def _demo(dry_run=True):
    ctx = _demo_context()
    print("\n" + "#" * 78)
    print("#  llm_client 드라이런 데모 — 실제 호출 없이 조립된 프롬프트를 확인합니다")
    print("#  (anthropic 설치=%s / ANTHROPIC_API_KEY=%s)"
          % (_ANTHROPIC_AVAILABLE, "설정" if os.environ.get("ANTHROPIC_API_KEY") else "없음"))
    print("#" * 78)

    print("\n[모델 매핑]")
    print("  면접관 대화     : %s" % MODEL_INTERVIEWER)
    print("  트리거/경량판정 : %s" % MODEL_LIGHTWEIGHT)
    print("  채점 앙상블     : %s" % MODEL_SCORER)

    itv = AnthropicInterviewerClient(dry_run=dry_run)

    print("\n>>> [1] 면접관 오프닝(intro) — 진행자(표준형)")
    print(itv.interviewer_turn("intro", context=ctx))

    print("\n>>> [2] 주질문(main) — 지역현안 / 표준형(위원B)")
    q = {"type": "지역현안", "text": "대구시의 청년 유출 문제에 대해 어떻게 생각하십니까?", "id": "q001"}
    print(itv.interviewer_turn("main", persona="표준형", context=ctx, question=q))

    print("\n>>> [3] 꼬리질문(followup) — T1 red flag / 압박형(위원C)")
    print(itv.interviewer_turn(
        "followup", persona="압박형", context=ctx, question=q,
        answer="민원인이 힘들어 보이면 규정을 조금 유연하게 적용해서라도 먼저 처리해 드리는 게 맞다고 봅니다.",
        trigger="T1", snippet="규정을 조금 유연하게 적용", depth=1))

    print("\n>>> [4] 경량 트리거 판정(detect_trigger) — Haiku")
    itv.detect_trigger(
        "주민과 항상 소통하며 최선을 다하는 공무원이 되겠습니다.",
        qtype="공직가치", difficulty="실전")

    print("\n>>> [5] 채점(score) — Opus / 엄격위원(J-STR)")
    scorer = AnthropicScorerClient(committee_id="J-STR", dry_run=dry_run)
    res = scorer.score(
        question="상사가 부당한 지시를 한다면 어떻게 하겠는가?",
        answer=("상사가 시키는 데에는 다 이유가 있다고 생각합니다. 설령 규정에 조금 어긋나더라도 "
                "일단 지시니까 따르겠습니다. 문제가 생기면 지시한 상사가 책임지는 것이지 신입인 제 "
                "책임은 아니라고 생각합니다."),
        question_type="상황형")
    print(res.get("_prompt") if isinstance(res, dict) and res.get("_dry_run") else
          json.dumps(res, ensure_ascii=False, indent=2))

    print("\n>>> [6] red flag 2차 판정(detect_red_flags) — Haiku / §3")
    rf = scorer.detect_red_flags(
        question="본인의 장점과 단점을 말해보라.",
        answer="저는 혼자 일할 때 성과가 잘 나옵니다. 팀 활동은 별로 선호하지 않습니다.",
        written_task="팀 활동에서 경청과 소통을 주도하는 것이 저의 최대 강점")
    print(rf.get("_prompt") if isinstance(rf, dict) and rf.get("_dry_run") else
          json.dumps(rf, ensure_ascii=False, indent=2))

    print("\n" + "#" * 78)
    print("#  드라이런 완료. 실제 호출: --live (anthropic 설치 + ANTHROPIC_API_KEY 필요)")
    print("#" * 78)


def main():
    ap = argparse.ArgumentParser(
        description="실제 Claude API 면접관·채점 어댑터 (드라이런/라이브)")
    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="실제 호출 없이 조립된 프롬프트만 출력(기본값)")
    ap.add_argument("--live", action="store_true",
                    help="실제 API 호출(anthropic 설치 + ANTHROPIC_API_KEY 필요)")
    args = ap.parse_args()
    _demo(dry_run=not args.live)


if __name__ == "__main__":
    main()
