#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
공무원 AI 모의면접 — 세션 오케스트레이터(면접관 대화 엔진) 프로토타입 (MVP)

설계 근거:
  - data/06-answer-guides/모의면접-세션-설계.md   §2 (세션 상태 머신, 꼬리질문 트리거 T1~T7)
  - data/08-system/면접관-페르소나-세트.md         (위원A/B/C 3인 페르소나, 지자체 압박계수)
  - data/08-system/prototype/question_selector.py  (질문 선택 엔진 — import 사용)
  - data/07-structured/region_context.json         (지역 컨텍스트: 시정비전·핵심사업·지역현안)
  - data/07-structured/job_context.json            (직렬 컨텍스트: 주요업무·핵심제도)

핵심 아이디어:
  question_selector.select_questions() 로 질문 큐를 만든 뒤, 상태 머신
    INTAKE → SPEECH_PREP → SPEECH → INTERVIEW(질문 루프) → WRAPUP → SCORING(스텁)
  을 돌린다. INTERVIEW 내부에서 각 답변마다 규칙 기반으로 꼬리질문 트리거(T1/T3/T4/T5/T6/T7)를
  판정하고, 트리거→페르소나(위원A/B/C) 매핑에 따라 꼬리질문을 생성한다.

LLM 호출부는 LLMClient 프로토콜로 추상화한다. 기본 제공되는 MockLLMClient 는
  규칙 기반(템플릿) 면접관 발화를 만들어 API 키 없이 결정적으로 동작한다.
  실제 서비스에서는 AnthropicLLMClient(하단, 연결 지점 주석 표시)로 교체한다.

표준 라이브러리만 사용. 동일 seed면 결과가 항상 동일(결정적).
"""

import argparse
import json
import os
import random
import re
from typing import Protocol

import question_selector as qs  # 같은 prototype/ 디렉터리의 질문 선택 엔진

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
REGION_CTX_PATH = os.path.join(_REPO_ROOT, "data", "07-structured", "region_context.json")
JOB_CTX_PATH = os.path.join(_REPO_ROOT, "data", "07-structured", "job_context.json")


# ===========================================================================
# 1. 페르소나 / 트리거 상수 (면접관-페르소나-세트.md, 세션-설계.md §2-2)
# ===========================================================================
PERSONA_LABEL = {"온화형": "위원A", "표준형": "위원B", "압박형": "위원C"}

# 트리거 → 발화 페르소나 (페르소나-세트.md §3 매핑표)
TRIGGER_PERSONA = {
    "T1": "압박형",  # red flag 소명
    "T3": "온화형",  # 경험 주장 STAR 검증
    "T4": "온화형",  # 추상어·선언 구체화
    "T5": "표준형",  # 정책·수치 지식 검증
    "T6": "압박형",  # 상황형 원칙답변 조건변경
    "T7": "온화형",  # 미완결 유도 재질문(코칭)
}
# 트리거별 최대 뎁스 (세션-설계.md §2-2 표)
TRIGGER_MAXDEPTH = {"T1": 1, "T3": 3, "T4": 2, "T5": 2, "T6": 3, "T7": 1}
TRIGGER_NAME = {
    "T1": "red flag(소명)",
    "T3": "경험주장(STAR)",
    "T4": "추상어(구체화)",
    "T5": "정책·수치(지식검증)",
    "T6": "원칙답변(조건변경)",
    "T7": "미완결(유도재질문)",
}
# 동시 다중 트리거 시 우선순위(세션-설계.md §107: T1>T2>…>T7). T2(진술모순)는
# 세션로그 의미 대조가 필요해 이 프로토타입에서는 미구현 → 목록에서 제외.
TRIGGER_PRIORITY = ["T1", "T3", "T4", "T5", "T6", "T7"]

# 주(主)질문을 던지는 페르소나 (유형별 담당, 페르소나-세트.md §1 표)
MAIN_PERSONA_BY_TYPE = {
    "인성": "온화형",
    "공직가치": "온화형",
    "직무": "표준형",
    "지역현안": "표준형",
    "상황형": "압박형",
}

# 지자체 프로파일: 페르소나 구성 + 압박계수(0.0~1.0) (페르소나-세트.md §2)
REGION_PROFILE = {
    "서울특별시": {"personas": ["온화형", "표준형"], "pressure": 0.4, "speech_sec": 300},
    "부산광역시": {"personas": ["온화형", "표준형"], "pressure": 0.2, "speech_sec": 180},
    "대구광역시": {"personas": ["온화형", "표준형", "압박형"], "pressure": 0.7, "speech_sec": 0},
    "인천광역시": {"personas": ["온화형", "표준형", "압박형"], "pressure": 0.5, "speech_sec": 0},
    "경기도": {"personas": ["온화형", "표준형", "압박형"], "pressure": 0.9, "speech_sec": 0},
    "_default": {"personas": ["온화형", "표준형", "압박형"], "pressure": 0.6, "speech_sec": 0},
}


# ===========================================================================
# 2. 규칙 기반 꼬리질문 트리거 판정 (실제 LLM 분석의 스텁)
#    세션-설계.md §2-2 의 "경량 LLM 1회 분석"을 키워드/휴리스틱으로 근사.
# ===========================================================================
RED_FLAG_KW = [  # T1: 규정 무시·사익 우선·책임 전가·반공직 가치관
    "규정을 조금 유연", "규정보다 융통성", "유연하게 적용", "융통성이 우선",
    "규정을 무시", "규정을 어기", "안 지켜도", "봐드리", "봐주", "편법",
    "적당히", "대충", "눈감", "사익", "개인적으로 이득", "책임은 상사",
    "상사 탓", "제 책임은 아니", "형평성은 무시",
]
EXPERIENCE_KW = [  # T3: 경험 주장
    "경험이 있습니다", "경험이 있어요", "한 적이 있습니다", "했었습니다",
    "이끈 경험", "이끌었", "봉사", "참여했습니다", "해봤습니다", "맡아서",
    "활동을 했", "프로젝트를 진행", "동아리",
]
ABSTRACT_KW = [  # T4: 추상어·선언 (구체 행동 없는 선언)
    "최선을 다", "열심히", "노력하겠", "소통하며", "소통하겠", "성실하게",
    "항상 소통", "언제나", "앞장서겠", "헌신하겠", "묵묵히", "최선을",
]
POLICY_KW = [  # T5: 정책명·사업명 (일반 토큰; 지역/직렬 컨텍스트 토큰은 런타임에 추가)
    "동행카드", "카드", "르네상스", "프로젝트", "특구", "신도시", "클러스터",
    "엑스포", "델타시티", "정책", "사업", "제도",
]
PRINCIPLE_KW = [  # T6: 상황형 교과서식 원칙 답변
    "법령", "규정", "확인하고", "재검토를 건의", "건의하겠", "절차에 따라",
    "보고하겠", "상급자", "규정대로", "원칙대로", "위법",
]
INCOMPLETE_KW = ["잘 모르겠", "모르겠습니다", "글쎄", "기억이 안", "생각이 안 나"]
NUM_RE = re.compile(r"\d+\s*(%|퍼센트|조|억|만\s*명|명|년|위)")


def _first_kw(text, kws):
    for kw in kws:
        if kw in text:
            return kw
    return None


def detect_specific(text, trigger, qtype, policy_terms):
    """단일 트리거 t 에 대한 감지 신호(snippet)를 반환. 없으면 None."""
    t = (text or "").strip()
    if trigger == "T1":
        return _first_kw(t, RED_FLAG_KW)
    if trigger == "T3":
        return _first_kw(t, EXPERIENCE_KW)
    if trigger == "T4":
        return _first_kw(t, ABSTRACT_KW)
    if trigger == "T5":
        kw = _first_kw(t, POLICY_KW) or _first_kw(t, policy_terms)
        if kw:
            return kw
        m = NUM_RE.search(t)
        return m.group(0) if m else None
    if trigger == "T6":
        if qtype != "상황형":  # 원칙답변 트리거는 상황형에서만
            return None
        return _first_kw(t, PRINCIPLE_KW)
    if trigger == "T7":
        if len(t) < 15:
            return t or "(무응답)"
        return _first_kw(t, INCOMPLETE_KW)
    return None


def detect_trigger(text, qtype, difficulty, policy_terms):
    """
    답변 전사문에서 우선순위(T1>…>T7)로 트리거 1개를 판정.
    세션-설계.md §107: 동시 다중 트리거 시 우선순위 높은 것 하나만 실행.
    초급 모드: T1(red flag)·T7(미완결)만 (설계 §4-1).
    반환: (trigger_id, snippet) 또는 (None, None)
    """
    allowed = {"T1", "T7"} if difficulty == "초급" else set(TRIGGER_PRIORITY)
    for t in TRIGGER_PRIORITY:
        if t not in allowed:
            continue
        snip = detect_specific(text, t, qtype, policy_terms)
        if snip:
            return t, snip
    return None, None


# ===========================================================================
# 3. LLMClient 프로토콜 + MockLLMClient
# ===========================================================================
class LLMClient(Protocol):
    """
    면접관 발화 생성 인터페이스. 세션 엔진은 오직 이 메서드만 호출한다.
    실제 서비스에서는 이 프로토콜을 구현한 Claude API 클라이언트를 주입한다
    (하단 AnthropicLLMClient 참고).

    kind:
      "intro"        세션 오프닝 안내 (컨텍스트 반영)
      "speech_prompt" 5분/3분 스피치 제시문 제시
      "speech_ack"   스피치 종료 후 짧은 반응
      "main"         주질문을 페르소나 어조로 발화 (컨텍스트 반영)
      "followup"     트리거 기반 꼬리질문 생성 (답변 인용)
      "wrapup"       마지막으로 하고 싶은 말 요청
      "closing"      면접 종료 멘트
    """

    def interviewer_turn(
        self,
        kind,
        *,
        persona=None,
        context=None,
        question=None,
        answer=None,
        trigger=None,
        snippet=None,
        depth=0,
    ) -> str:
        ...


class MockLLMClient:
    """
    규칙 기반(템플릿) 면접관 발화 생성기. API 키 불필요·결정적.
    페르소나별 말투(면접관-페르소나-세트.md §1 말투 샘플)와
    트리거별 대사(§3 실제 대사 예시)를 템플릿으로 재현한다.
    자료(context)에 없는 정책명·수치를 지어내지 않는다(§5 가드레일 5).
    """

    def interviewer_turn(
        self, kind, *, persona=None, context=None, question=None,
        answer=None, trigger=None, snippet=None, depth=0,
    ) -> str:
        if kind == "intro":
            return self._intro(context)
        if kind == "speech_prompt":
            return self._speech_prompt(context)
        if kind == "speech_ack":
            return "네, 잘 들었습니다. 발표 내용과 관련해서도 이어서 여쭙겠습니다."
        if kind == "main":
            return self._main(persona, question, context)
        if kind == "followup":
            return self._followup(persona, trigger, snippet, depth, question, context)
        if kind == "wrapup":
            return "마지막으로 하고 싶은 말씀이 있으면 편하게 해 주세요."
        if kind == "closing":
            return "면접에 응해 주셔서 감사합니다. 수고하셨습니다."
        return "(발화 없음)"

    # --- 오프닝: 지역/직렬 컨텍스트 반영 --------------------------------
    def _intro(self, ctx):
        r, j = ctx["region"], ctx["job"]
        lead = f"{r} {j} 면접에 오신 것을 환영합니다. 저는 진행을 맡은 위원B입니다."
        bits = []
        vision = ctx.get("시정비전") or ""
        slogan = ctx.get("슬로건") or ""
        if slogan:
            bits.append(f"{r}는 '{slogan}'을(를) 시정 기조로 두고 있습니다.")
        elif vision:
            bits.append(f"{r} 시정 기조는 \"{vision[:40]}\" 입니다.")
        duty = ctx.get("주요업무") or []
        if duty:
            first = duty[0].split(":")[0].split("(")[0].strip()
            bits.append(f"{j}은(는) 주로 '{first}' 등의 업무를 맡습니다.")
        guide = (
            f"본 모의면접은 [{ctx['track']} 트랙 · {ctx['difficulty']} 모드]로 진행되며, "
            f"참여 위원은 {'·'.join(PERSONA_LABEL[p] for p in ctx['personas'])} 입니다. "
            "제도는 응시 연도별로 달라질 수 있으니 실제 공고문을 확인하세요."
        )
        return lead + (" " + " ".join(bits) if bits else "") + "\n    " + guide

    # --- 스피치 제시문 ------------------------------------------------
    def _speech_prompt(self, ctx):
        sec = ctx.get("speech_sec") or 300
        mins = sec // 60
        # 컨텍스트 내 지역현안 1건을 소재로 사용(자료 밖 사실 생성 금지).
        issues = ctx.get("지역현안") or []
        topic = issues[0] if issues else "공직자가 갖춰야 할 적극행정의 의미"
        topic = topic.split("(")[0].strip()
        return (
            f"[스피치 제시문] '{topic}'에 대한 본인의 생각을, {mins}분 내외로 발표해 주세요. "
            f"준비 시간 동안 메모하셔도 좋습니다. (목표 {mins}분)"
        )

    # --- 주질문: 페르소나 어조 + 지역현안 컨텍스트 ---------------------
    def _main(self, persona, q, ctx):
        text = (q.get("text") or "").replace("\n", " ").strip()
        qtype = q.get("type")
        prefix = ""
        # 지역현안 주질문에는 컨텍스트(자료 내 현안)를 한 문장 얹는다.
        if qtype == "지역현안":
            issues = ctx.get("지역현안") or []
            if issues:
                iss = issues[0].split("(")[0].strip()
                if iss and iss not in text:
                    prefix = f"{ctx['region']}은(는) '{iss}' 같은 현안이 있습니다. "
        if persona == "온화형":
            return f"네, 편하게 말씀하셔도 됩니다. {prefix}{text}"
        if persona == "표준형":
            return f"그럼 여쭙겠습니다. {prefix}{text}"
        if persona == "압박형":
            return f"{prefix}{text} 구체적으로 말씀해 주세요."
        return prefix + text

    # --- 꼬리질문: 트리거별 대사(답변 표현 인용) ----------------------
    def _followup(self, persona, trigger, snippet, depth, q, ctx):
        s = snippet or ""
        if trigger == "T1":  # 압박형: 소명 요구 1회 (비난 없이)
            return (
                f"방금 '{s}'(이)라고 하셨는데, 그렇게 판단하신 근거는 무엇입니까? "
                "다른 민원인과의 형평성 문제는 어떻게 보시는지요?"
            )
        if trigger == "T3":  # 온화형: STAR 단계별
            steps = [
                f"좋은 경험이네요. 그때 본인이 맡았던 역할은 무엇이었어요?",
                "그 상황에서 구체적으로 어떻게 하셨는지 조금 더 들려주시겠어요?",
                "그 경험에서 새롭게 배운 점이 있다면요?",
            ]
            return steps[min(depth - 1, len(steps) - 1)]
        if trigger == "T4":  # 온화형: 구체화 요구
            steps = [
                f"'{s}'고 하셨는데, 실제 업무에서 구체적으로 어떤 방법으로 하실 생각인가요?",
                "예를 들어 하나만 들어 주시겠어요?",
            ]
            return steps[min(depth - 1, len(steps) - 1)]
        if trigger == "T5":  # 표준형: 한계·보완점
            steps = [
                f"'{s}'을(를) 언급하셨는데, 그 정책의 한계나 담당자로서 보완할 점은 무엇이라고 보십니까?",
                "그 부분을 실제로 개선하려면 어떤 절차가 필요할까요?",
            ]
            return steps[min(depth - 1, len(steps) - 1)]
        if trigger == "T6":  # 압박형: 조건변경 → 원칙 흔들기
            steps = [
                "말씀하신 원칙은 알겠습니다. 그런데 상사가 '내가 책임질 테니 그대로 진행하라'고 "
                "다시 지시하면, 그때는 어떻게 하시겠습니까?",
                "명백한 위법까지는 아니고 관행과 규정 사이의 회색지대라면, 판단 기준을 어디에 두시겠습니까?",
                "정리하면, 최종적으로 어떤 선택을 하시겠다는 말씀인가요?",
            ]
            return steps[min(depth - 1, len(steps) - 1)]
        if trigger == "T7":  # 온화형: 유도 재질문(압박 아님)
            return (
                "괜찮습니다. 정답이 있는 질문은 아니에요. 조금 더 구체적으로 말씀해 주시겠어요? "
                "예를 들면 학교나 직장에서의 사례도 좋습니다."
            )
        return "조금 더 말씀해 주시겠어요?"


# --- 실제 Claude API 연결 지점 ------------------------------------------
class AnthropicLLMClient:
    """
    ★★★ 실제 LLM(Claude) 연결 지점 ★★★

    MockLLMClient 를 이 클래스로 교체하면 규칙 템플릿 대신 실제 면접관 발화를
    생성한다. 세션 엔진 코드는 한 줄도 바꾸지 않는다(LLMClient 프로토콜 준수).

    실제 구현 시:
      1) pip install anthropic  (표준 라이브러리 밖 — 프로토타입 기본 실행에는 불필요)
      2) 페르소나별 시스템 프롬프트 = 면접관-페르소나-세트.md §1-1/1-2/1-3 프롬프트 +
         §5 하드 가드레일. context(지역/직렬 자료)를 [지자체 컨텍스트]/[직렬 컨텍스트]로 주입.
      3) 꼬리질문 온도 0.3 권장(페르소나-세트.md §3, 답변 인용 정확성 우선).
    """

    def __init__(self, model="claude-opus-4-8", api_key=None):
        self.model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        # self._client = anthropic.Anthropic(api_key=self._api_key)   # ← 실제 연결

    def interviewer_turn(self, kind, *, persona=None, context=None, question=None,
                         answer=None, trigger=None, snippet=None, depth=0) -> str:
        # system = build_persona_system_prompt(persona, context)   # §1 + §5 가드레일
        # user   = build_turn_user_prompt(kind, question, answer, trigger, snippet, depth)
        # resp = self._client.messages.create(
        #     model=self.model, max_tokens=256, temperature=0.3,
        #     system=system, messages=[{"role": "user", "content": user}],
        # )
        # return resp.content[0].text.strip()
        raise NotImplementedError(
            "실제 Claude 연동은 이 지점에서 구현. 프로토타입은 MockLLMClient 사용."
        )


# ===========================================================================
# 4. 답변 제공자 (데모 모드 / stdin 모드)
# ===========================================================================
# 데모용 미리 정의 답변: 유형별로 트리거를 하나씩 유발하도록 설계.
# (T1 red flag / T3 경험 / T4 추상어 / T5 정책 / T6 원칙 / T7 미완결 모두 시연)
_DEMO_MAIN_ANSWERS = {
    "인성": [
        "학창 시절 봉사 동아리 회장으로 팀을 이끈 경험이 있습니다. 그때 정말 열심히 했습니다.",  # T3
        "주변에서는 꼼꼼하다는 말을 자주 합니다. 자료를 정리해 공유하는 편입니다.",              # resolved
        "스트레스가 쌓이면 30분씩 걷고 다음 날 우선순위를 다시 정리합니다.",                    # resolved
    ],
    "공직가치": [
        "주민과 항상 소통하며 최선을 다하는 공무원이 되겠습니다.",                              # T4
        "청렴은 공직 신뢰의 기본이라, 작은 선물도 규정에 따라 정중히 거절하겠습니다.",           # resolved
    ],
    "직무": [
        "민원인이 많이 힘들어 보이면 규정을 조금 유연하게 적용해서라도 먼저 처리해 드리는 게 맞다고 봅니다.",  # T1
        "잘 모르겠습니다.",                                                                    # T7
        "행정심판은 행정청이, 행정소송은 법원이 판단한다는 절차상 차이가 있습니다.",             # resolved
    ],
    "지역현안": [
        "에코델타시티 개발 사업이 활발하게 진행되고 있는 것으로 알고 있습니다.",                 # T5
        "원도심 공동화 문제에 관심이 있고, 생활 인프라 확충이 필요하다고 생각합니다.",           # resolved
    ],
    "상황형": [
        "먼저 관련 법령을 다시 확인하고, 위법 소지가 있으면 재검토를 건의하겠습니다.",           # T6
    ],
}

# 트리거별 꼬리질문에 대한 데모 답변(뎁스 진행 시연)
_DEMO_FOLLOWUP_ANSWERS = {
    "T1": ["다른 분과의 형평성도 중요하니, 규정 안에서 최대한 빨리 처리할 방법을 찾겠습니다."],
    "T3": [
        "네, 봉사 일정을 짜고 팀원들의 의견을 조율하는 역할을 맡았습니다.",   # 여전히 '봉사' 포함 → 뎁스2
        "갈등이 있을 때 먼저 상대의 말을 끝까지 듣는 게 중요하다는 걸 배웠습니다.",  # resolved
    ],
    "T4": ["주 1회 현장 방문과 온라인 게시판 운영으로 주민 의견을 듣겠습니다."],
    "T5": ["재정 부담이 한계라고 보고, 대상을 단계적으로 넓히는 보완이 필요하다고 생각합니다."],
    "T6": [
        "그래도 명백히 위법하다면 규정을 근거로 따를 수 없다고 말씀드리겠습니다.",  # '규정','위법' → 뎁스2
        "공익과 규정 준수 사이의 균형을 기준으로 판단하겠습니다.",                # '규정' → 뎁스3
        "최종적으로는 규정을 지키되 상급자에게 정식 절차로 재검토를 요청하겠습니다.",  # 마무리
    ],
    "T7": ["죄송합니다. 학교 조별과제에서 역할을 나눠 기한을 맞춘 경험이 있습니다."],
}


class DemoAnswerProvider:
    """미리 정의된 답변을 결정적으로 반환(데모/자동 시연)."""

    def __init__(self):
        self._counter = {}

    def main(self, qtype, question_text):
        pool = _DEMO_MAIN_ANSWERS.get(qtype, ["네, 성실히 임하겠습니다."])
        i = self._counter.get(qtype, 0)
        self._counter[qtype] = i + 1
        return pool[min(i, len(pool) - 1)]

    def followup(self, trigger, depth):
        pool = _DEMO_FOLLOWUP_ANSWERS.get(trigger, ["네, 알겠습니다."])
        return pool[min(depth - 1, len(pool) - 1)]

    def speech(self, ctx):
        return (
            "저는 이 현안이 주민 삶과 직결된다고 봅니다. 담당자가 되면 현장 목소리를 먼저 듣고, "
            "관련 부서와 협업해 단계적으로 해결하겠습니다. 감사합니다."
        )

    def wrapup(self):
        return "부족하지만 성실히 배우는 공무원이 되겠습니다. 감사합니다."


class StdinAnswerProvider:
    """실제 사용자 입력(stdin)으로 답변을 받는다(--interactive)."""

    def main(self, qtype, question_text):
        return input("    (지원자 답변) > ").strip()

    def followup(self, trigger, depth):
        return input("    (지원자 답변) > ").strip()

    def speech(self, ctx):
        return input("    (지원자 발표) > ").strip()

    def wrapup(self):
        return input("    (지원자 답변) > ").strip()


# ===========================================================================
# 5. 컨텍스트 로더
# ===========================================================================
def load_context():
    with open(REGION_CTX_PATH, "r", encoding="utf-8") as f:
        region_ctx = json.load(f)
    with open(JOB_CTX_PATH, "r", encoding="utf-8") as f:
        job_ctx = json.load(f)
    return region_ctx, job_ctx


def find_region_ctx(region_ctx, region):
    for r in region_ctx:
        if r.get("region") == region:
            return r
    return {}


def find_job_ctx(job_ctx, job):
    # 정확 일치 → 괄호 접두 일치(예: '소방직' → '소방직(소방)')
    for j in job_ctx:
        if j.get("job") == job:
            return j
    for j in job_ctx:
        base = j.get("job", "").split("(")[0]
        if base == job or job.startswith(base) or base.startswith(job):
            return j
    return {}


def build_policy_terms(region_c, job_c):
    """컨텍스트에서 T5(정책·수치) 감지용 키워드 집합을 추출(길이 3+ 토큰)."""
    terms = set()
    for src in (region_c.get("핵심사업", []), region_c.get("지역현안", []),
                job_c.get("핵심제도", [])):
        for phrase in src:
            for tok in re.split(r"[\s·,()\[\]/~]+", str(phrase)):
                tok = tok.strip()
                if len(tok) >= 3:
                    terms.add(tok)
    return list(terms)


# ===========================================================================
# 6. 세션 엔진 (상태 머신)
# ===========================================================================
STATES = ["INTAKE", "SPEECH_PREP", "SPEECH", "INTERVIEW", "WRAPUP", "SCORING"]


class SessionEngine:
    def __init__(self, region, job, track="지방직표준", difficulty="실전",
                 llm=None, provider=None, seed=42, questions=None):
        self.region = region
        self.job = job
        self.track = track
        self.difficulty = difficulty
        self.seed = seed
        self.llm = llm or MockLLMClient()
        self.provider = provider or DemoAnswerProvider()

        # 압박계수·페르소나 로스터 (지자체 프로파일)
        prof = REGION_PROFILE.get(region, REGION_PROFILE["_default"])
        self.personas = prof["personas"]
        self.pressure = prof["pressure"]
        self.speech_sec = prof.get("speech_sec", 300) or 300
        # 압박계수 판정용 RNG(질문선택 seed와 분리, 결정적)
        self.prng = random.Random(seed ^ 0x9E3779B9)

        # 컨텍스트
        region_all, job_all = load_context()
        self.region_c = find_region_ctx(region_all, region)
        self.job_c = find_job_ctx(job_all, job)
        self.policy_terms = build_policy_terms(self.region_c, self.job_c)

        # 질문 큐 (question_selector 사용)
        self._questions = questions if questions is not None else qs.load_questions()
        self.plan = qs.select_questions(
            region=region, job=job, track=track, difficulty=difficulty,
            questions=self._questions, seed=seed,
        )
        self.seq = self.plan["seq"]

        # 꼬리질문 예산: 총 주질문의 60% 정도 (세션-설계.md §108, 40% 시간 예산 근사)
        self.followup_budget = max(4, round(len(self.seq) * 0.6))
        self.followups_used = 0

        # 세션 로그 (채점 파이프라인 입력 · 일관성 red flag 대조용)
        self.log = []
        self.t = 0

        # LLM 에 넘기는 컨텍스트 dict
        self.ctx = {
            "region": region, "job": job, "track": track, "difficulty": difficulty,
            "personas": self.personas, "pressure": self.pressure,
            "speech_sec": self.speech_sec,
            "시정비전": self.region_c.get("시정비전", ""),
            "슬로건": self.region_c.get("슬로건", ""),
            "지역현안": self.region_c.get("지역현안", []),
            "핵심사업": self.region_c.get("핵심사업", []),
            "주요업무": self.job_c.get("주요업무", []),
            "핵심제도": self.job_c.get("핵심제도", []),
        }

    # -- 로깅/출력 --------------------------------------------------------
    def _emit(self, state, role, text, persona=None, qid=None, trigger=None):
        self.t += 1
        self.log.append({
            "t": self.t, "state": state, "role": role, "persona": persona,
            "qid": qid, "trigger": trigger, "text": text,
        })
        if role == "면접관":
            tag = f"{PERSONA_LABEL[persona]}/{persona}" if persona else "진행"
            print(f"[t{self.t:03d}][{state}][{tag}] {text}")
        elif role == "지원자":
            print(f"        (지원자) {text}")
        elif role == "시스템":
            print(f"   ↳ {text}")

    def _resolve_persona(self, persona):
        """로스터에 없는 페르소나(예: 2인 트랙의 압박형)는 표준형이 흡수(설계 §221)."""
        if persona in self.personas:
            return persona, False
        return "표준형", True  # (실제사용 페르소나, 흡수여부)

    # -- 상태: INTAKE -----------------------------------------------------
    def _state_intake(self):
        print("\n" + "=" * 78)
        print(f" 세션 시작  |  {self.region} · {self.job} · 트랙={self.track} · "
              f"난이도={self.difficulty} · 압박계수={self.pressure} · seed={self.seed}")
        print("=" * 78)
        intro = self.llm.interviewer_turn("intro", context=self.ctx)
        self._emit("INTAKE", "면접관", intro)

    # -- 상태: SPEECH_PREP / SPEECH --------------------------------------
    def _state_speech(self):
        prompt = self.llm.interviewer_turn("speech_prompt", context=self.ctx)
        self._emit("SPEECH_PREP", "면접관", prompt)
        speech = self.provider.speech(self.ctx)
        self._emit("SPEECH", "지원자", speech)
        ack = self.llm.interviewer_turn("speech_ack", context=self.ctx)
        self._emit("SPEECH", "면접관", ack)

    # -- 상태: INTERVIEW (질문 루프 + 꼬리질문) ---------------------------
    def _pressure_gate(self, trigger):
        """압박형 트리거(T1/T6)는 지자체 압박계수 확률로 발화(설계 §144, 결정적)."""
        if TRIGGER_PERSONA[trigger] != "압박형":
            return True, None
        roll = self.prng.random()
        fired = roll < self.pressure
        note = f"압박계수 {self.pressure} · roll={roll:.2f} → {'실행' if fired else '스킵'}"
        return fired, note

    def _run_followups(self, main_q, first_answer):
        qtype = main_q.get("type")
        qid = main_q.get("id")
        answer = first_answer
        prev_trigger = None
        while True:
            trigger, snippet = detect_trigger(answer, qtype, self.difficulty, self.policy_terms)
            if not trigger:
                break
            # 뎁스는 주질문 단위. 같은 트리거 계열로만 이어감.
            if prev_trigger is None:
                prev_trigger = trigger
                depth = 0
            elif trigger != prev_trigger:
                break  # 다른 트리거로 바뀌면 종료(단일 트리거 원칙)
            if depth >= TRIGGER_MAXDEPTH[trigger]:
                break
            if self.followups_used >= self.followup_budget:
                self._emit("INTERVIEW", "시스템",
                           f"[꼬리질문 예산 소진({self.followup_budget}) → 통과]", qid=qid)
                break
            # 압박계수 게이트
            fired, note = self._pressure_gate(trigger)
            persona, absorbed = self._resolve_persona(TRIGGER_PERSONA[trigger])
            if not fired:
                self._emit("INTERVIEW", "시스템",
                           f"[트리거 {trigger} {TRIGGER_NAME[trigger]} 감지 · {note}]", qid=qid)
                break
            depth += 1
            self.followups_used += 1
            absorb = " · 압박형→표준형 흡수(2인 트랙)" if absorbed else ""
            gate = f" · {note}" if note else ""
            self._emit("INTERVIEW", "시스템",
                       f"[트리거 {trigger} {TRIGGER_NAME[trigger]} 감지: '{snippet}' → "
                       f"{PERSONA_LABEL[persona]} 꼬리질문 (뎁스 {depth}/{TRIGGER_MAXDEPTH[trigger]})"
                       f"{gate}{absorb}]", qid=qid, trigger=trigger)
            fq = self.llm.interviewer_turn(
                "followup", persona=persona, context=self.ctx,
                question=main_q, answer=answer, trigger=trigger,
                snippet=snippet, depth=depth,
            )
            self._emit("INTERVIEW", "면접관", fq, persona=persona, qid=qid, trigger=trigger)
            answer = self.provider.followup(trigger, depth)
            self._emit("INTERVIEW", "지원자", answer, qid=qid, trigger=trigger)

    def _state_interview(self):
        for item in self.seq:
            q = item["question"]
            qtype = q.get("type")
            base_persona = MAIN_PERSONA_BY_TYPE.get(qtype, "표준형")
            persona, _ = self._resolve_persona(base_persona)
            ask = self.llm.interviewer_turn("main", persona=persona, context=self.ctx, question=q)
            self._emit("INTERVIEW", "면접관", ask, persona=persona, qid=q.get("id"))
            answer = self.provider.main(qtype, q.get("text", ""))
            self._emit("INTERVIEW", "지원자", answer, qid=q.get("id"))
            self._run_followups(q, answer)

    # -- 상태: WRAPUP -----------------------------------------------------
    def _state_wrapup(self):
        ask = self.llm.interviewer_turn("wrapup", context=self.ctx)
        self._emit("WRAPUP", "면접관", ask)
        ans = self.provider.wrapup()
        self._emit("WRAPUP", "지원자", ans)
        self._emit("WRAPUP", "면접관", self.llm.interviewer_turn("closing", context=self.ctx))

    # -- 상태: SCORING (스텁) --------------------------------------------
    def _state_scoring(self):
        # 실제 채점은 평가루브릭-설계.md §4-3 파이프라인 연결 지점.
        # 여기서는 세션 로그를 집계해 채점 입력 신호만 요약한다(스텁).
        redflags = [l for l in self.log if l["trigger"] == "T1" and l["role"] == "면접관"]
        incompletes = [l for l in self.log if l["trigger"] == "T7" and l["role"] == "면접관"]
        followups = [l for l in self.log if l["role"] == "면접관" and l["trigger"]]
        by_trig = {}
        for l in followups:
            by_trig[l["trigger"]] = by_trig.get(l["trigger"], 0) + 1
        print("-" * 78)
        print("[SCORING · 스텁] 실제 채점은 평가루브릭-설계.md §4-3 파이프라인 연결 지점")
        print(f"  · 주질문 {len(self.seq)}개, 꼬리질문 {len(followups)}개"
              f"(예산 {self.followup_budget}), 총 발화 {self.t}턴")
        print(f"  · 트리거 발동: " + (", ".join(f"{k}×{v}" for k, v in sorted(by_trig.items())) or "없음"))
        print(f"  · red flag(T1) 소명요구 {len(redflags)}건, 미완결(T7) 재질문 {len(incompletes)}건")
        print(f"  · 참여 위원: {'·'.join(PERSONA_LABEL[p]+'('+p+')' for p in self.personas)}"
              f" / 판정 규칙: {'만장일치(2인)' if len(self.personas)==2 else '2/3 다수결(3인)'}")
        print("  · 다음 단계(미구현): STT 스피치지표 → 페르소나 앙상블 채점 → 과반 집계 → FEEDBACK")
        print("=" * 78)

    # -- 실행 -------------------------------------------------------------
    def run(self):
        self._state_intake()
        self._state_speech()
        self._state_interview()
        self._state_wrapup()
        self._state_scoring()
        return self.log


# ===========================================================================
# 7. CLI
# ===========================================================================
def main():
    ap = argparse.ArgumentParser(
        description="공무원 AI 모의면접 세션 오케스트레이터 프로토타입"
    )
    ap.add_argument("--region", required=True, help="지자체명 (예: 서울특별시)")
    ap.add_argument("--job", required=True, help="직렬명 (예: 일반행정직)")
    ap.add_argument("--track", default="지방직표준",
                    choices=list(qs.QUOTA_TRACKS.keys()), help="면접 트랙")
    ap.add_argument("--difficulty", default="실전", choices=["실전", "초급"],
                    help="난이도 모드")
    ap.add_argument("--seed", type=int, default=42, help="랜덤 시드")
    ap.add_argument("--interactive", action="store_true",
                    help="stdin으로 직접 답변 입력(기본: 데모 자동 답변)")
    args = ap.parse_args()

    provider = StdinAnswerProvider() if args.interactive else DemoAnswerProvider()
    engine = SessionEngine(
        region=args.region, job=args.job, track=args.track,
        difficulty=args.difficulty, seed=args.seed,
        llm=MockLLMClient(), provider=provider,
    )
    engine.run()


if __name__ == "__main__":
    main()
