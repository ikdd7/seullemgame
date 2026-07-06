# -*- coding: utf-8 -*-
"""
scorer.py — 공무원 AI 면접 채점 엔진 프로토타입 (Python 표준 라이브러리만)

설계 원천:
- data/08-system/채점-프롬프트-실장.md  (§1 채점 스키마, §2 앙상블 집계 로직)
- data/06-answer-guides/평가루브릭-설계.md (§1-2 등급 규칙, §2 요소별 하위지표)
- data/06-answer-guides/골든셋-답변예시.md (few-shot 앵커, 회귀 정답 레이블)

핵심:
- score_answer(...)      → 위원 1인이 답변 1개를 4대 평정요소(상/중/하)로 채점한 JSON 반환.
- LLMClient (추상)       → 실제 LLM API 채점기가 구현할 인터페이스.
- MockScorer            → 규칙 기반(길이·키워드·red flag 표현)으로 API 키 없이 데모.
- aggregate_verdicts(...)→ 위원 N명 결과를 §2-2 과반수 규칙으로 우수/보통/미흡 종합.
- score_session(...)     → 여러 문항을 N위원으로 채점 + 세션 집계 (피드백 리포트 입력).

주의: MockScorer는 규칙 기반 근사치로, **실제 채점 품질이 아니라 파이프라인 데모**용이다.
'하'는 (미흡 보수 판정 원칙에 따라) red flag 표현 감지로만 부여한다. 버벅임·짧은 답변·
긴장은 감점 사유로 쓰지 않는다. 실제 판정은 LLM 채점기(§1 프롬프트)가 담당한다.

표준 라이브러리만 사용. 결정적(deterministic): 같은 입력 → 같은 출력, 난수 없음.
"""

import re
import json
import argparse

# ---------------------------------------------------------------------------
# 상수 (채점-프롬프트-실장.md §2-2 / 평가루브릭-설계.md §1-2 계승)
# ---------------------------------------------------------------------------

ELEMENTS = ["소통공감", "헌신열정", "창의혁신", "윤리책임"]
RANK = {"상": 2, "중": 1, "하": 0}
INV_RANK = {2: "상", 1: "중", 0: "하"}

# 위원 페르소나 (§1-3). MockScorer는 규칙 공유가 원칙이라 red flag 동작은 동일하고,
# '경계(중/상)'에서만 아주 약간의 기질 차이를 결정적으로 적용한다(데모용).
COMMITTEE_PERSONAS = {
    "J-STD": "표준위원 — 기준값. 확신 없으면 '중'.",
    "J-STR": "엄격위원 — red flag·일관성에 민감(단 유창성·긴장으로는 감점 금지).",
    "J-JOB": "직무위원 — 직무/현안 정확성 중시(세부 조문 암기 부재는 감점 금지).",
}

LENGTH_GATE = 150   # 공백·괄호지문 제외 글자수. 이 이상 + 키워드 충족 시 '상' 후보.

# 요소별 긍정 신호 키워드 (평가루브릭-설계.md §2 하위지표 → 관찰 키워드로 축약)
POSITIVE_KEYWORDS = {
    "소통공감": ["입장", "관점", "말씀", "경청", "공감", "이해", "민원", "동료", "상사",
               "주민", "어르신", "상대", "함께", "소통", "협의", "듣", "여쭙", "설명드",
               "국민", "약속"],
    "헌신열정": ["먼저", "직접", "나서", "준비", "경험", "노력", "끝까지", "완수", "극복",
               "헌법", "공익", "봉사", "책임지", "의미", "활동", "배웠", "역할", "보호",
               "적극", "위해", "지원했", "결심"],
    "창의혁신": ["절차", "단계", "대안", "방안", "우선순위", "검토", "건의", "제도", "개선",
               "근거", "방법", "조율", "분담", "확인", "연계", "예방", "구조", "전략"],
    "윤리책임": ["법령", "규정", "원칙", "책임", "보고", "협의", "청렴", "공정", "행동강령",
               "신고", "정직", "공익", "준수", "기준", "형평", "절차"],
}

# red flag 표현 테이블 (채점-프롬프트-실장.md §1 red flag + 골든셋 미흡 앵커에서 추출).
# 각 규칙: 매칭 시 elements 를 강제 '하'. patterns 는 부분문자열(원문 그대로) 매칭.
RED_FLAG_RULES = [
    {
        "type": "반공직가치관", "elements": ["헌신열정", "윤리책임"],
        "patterns": [
            "봉사정신이나 사명감 같은 걸로", "월급 받는 성실한 직장인",
            "월급 받고 일하는 건 똑같", "잘리지 않는 직업", "잘리지 않으니까",
            "정년이 보장되니까", "안정적이고 정년", "제 생활이 먼저", "제 삶을 포기",
            "공무원도 결국 하나의 직업", "특별히 하고 싶은 업무가 있는 것은 아니",
        ],
        "note": "공직 동기 부재·공직가치 부정(반공직 발화)",
    },
    {
        "type": "위법정당화", "elements": ["윤리책임", "창의혁신"],
        "patterns": [
            "규정에 조금 어긋나더라도", "유연하게 해석해서라도", "융통성 있게 받",
            "규정을 어겨", "규정 때문에 못 돕는 것은 말이 안",
        ],
        "note": "위법·규정 위반의 정당화(선의로 포장돼도 트리거)",
    },
    {
        "type": "은폐책임전가", "elements": ["윤리책임"],
        "patterns": [
            "제 책임은 아니", "조용히 넘어가", "모른 척", "제 일도 아닌데",
            "들여다보는 사람도 없", "자세히 보는 사람도 없", "일을 키우기보다는 조용히",
        ],
        "note": "책임 전가·비위 은폐 의사",
    },
    {
        "type": "타인비하비협조", "elements": ["소통공감", "헌신열정"],
        "patterns": [
            "게으르고 개념이 없", "대화 자체가 안 통", "상대하지 않는 것이 답",
            "상대하지 않는 것이 맞", "진상", "팀 활동은 별로 선호하지 않",
        ],
        "note": "타인 비하·협업/응대 거부",
    },
    {
        "type": "답변포기자기붕괴", "elements": ["소통공감", "헌신열정"],
        "patterns": [
            "시키시는 대로 하겠습니다", "계속 다닐 수 있을지 잘 모르겠",
            "계속 다닐 수 있을지 모르겠",
        ],
        "note": "답변 포기·직무 지속 유보(회복 시도 없는 붕괴)",
    },
]

_PAREN_RE = re.compile(r"[(（\[].*?[)）\]]")   # 괄호 지문(관찰정보) 제거용
_SENT_RE = re.compile(r"(?<=[.!?…｡])\s+")


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------

def _spoken_text(answer):
    """괄호 안 관찰지문(침묵·서면내용 등)을 제거한 순수 발화 텍스트."""
    return _PAREN_RE.sub(" ", answer).strip()


def _dense_len(text):
    """공백 제외 글자수."""
    return len(re.sub(r"\s+", "", text))


def _sentences(text):
    return [s.strip() for s in _SENT_RE.split(text) if s.strip()]


def _find_quote(text, needle):
    """needle 을 포함하는 문장을 근거 인용으로 반환(없으면 needle 자체)."""
    for s in _sentences(text):
        if needle in s:
            return s
    return needle


def _first_quote(text):
    sents = _sentences(text)
    return sents[0] if sents else text.strip()


# ---------------------------------------------------------------------------
# LLM 클라이언트 추상화
# ---------------------------------------------------------------------------

class LLMClient(object):
    """
    채점기 인터페이스. 실제 구현체는 §1 System/User 프롬프트로 LLM을 호출하고
    §1-4 JSON 스키마를 파싱해 반환한다. (실제 연결 지점은 README 참고)
    """

    def score(self, question, answer, rubric=None, written_task=None,
              prev_answers=None, region_context=None, question_type=None):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 규칙 기반 Mock 채점기
# ---------------------------------------------------------------------------

class MockScorer(LLMClient):
    """
    규칙 기반 데모 채점기. API 키 없이 결정적으로 §1-4 스키마 JSON을 생성한다.

    판정 로직(요약):
      1) red flag 표현 감지 → 해당 요소 강제 '하'(하드 트리거).
      2) 서면 과제 대비 모순 감지(있을 때만) → 윤리책임·소통공감 강제 '하'.
      3) 강제되지 않은 요소는 (키워드 신호 ≥2) AND (발화 길이 ≥ LENGTH_GATE) → '상',
         그 외 '중'. (미흡 보수 판정: '하'는 red flag 로만 부여)
      4) member_grade = §1-4 위원 개인 규칙.
    """

    def __init__(self, committee_id="J-STD"):
        if committee_id not in COMMITTEE_PERSONAS:
            raise ValueError("unknown committee_id: %s" % committee_id)
        self.committee_id = committee_id

    # --- red flag / 모순 탐지 ------------------------------------------------

    def _detect_red_flags(self, answer, written_task=None):
        """감지된 red flag 목록(스키마 §1-4 red_flags 형식) 반환."""
        flags = []
        for rule in RED_FLAG_RULES:
            for pat in rule["patterns"]:
                if pat in answer:
                    quote = _find_quote(answer, pat)
                    # 규칙이 여러 요소를 강제하면 각 요소로 flag 를 남긴다.
                    for el in rule["elements"]:
                        flags.append({
                            "type": rule["type"],
                            "element": el,
                            "quote": quote,
                            "note": rule["note"],
                        })
                    break  # 같은 규칙 내 중복 패턴은 1회만
        # 서면 과제 대비 일관성 붕괴(§3 ⑤): written_task 있을 때만 판정 가능
        contra = self._detect_contradiction(answer, written_task)
        if contra:
            flags.append(contra)
        return flags

    @staticmethod
    def _detect_contradiction(answer, written_task):
        if not written_task:
            return None
        spoken = _spoken_text(answer)
        # 매우 단순한 반례 규칙(데모): 서면은 '팀/소통/협업 강점' 주장,
        # 구두는 '혼자/팀 비선호'로 뒤집는 경우.
        wt = written_task
        team_claim = any(k in wt for k in ["소통", "경청", "팀", "협업", "협력"])
        deny = any(k in spoken for k in ["혼자 일할 때", "팀 활동은 별로 선호하지 않",
                                          "팀으로 일하면 속도가 안 맞"])
        if team_claim and deny:
            return {
                "type": "진술모순",
                "element": "윤리책임",
                "quote": _find_quote(spoken, "선호하지 않") if "선호하지 않" in spoken
                         else spoken[:40],
                "note": "서면 과제(강점=소통/팀 주도)와 구두 답변(팀 비선호)이 해소 불가 모순",
            }
        return None

    # --- 요소 채점 -----------------------------------------------------------

    def _keyword_score(self, element, spoken):
        hits = [kw for kw in POSITIVE_KEYWORDS[element] if kw in spoken]
        score = len(set(hits))
        # '근거(수치·사례)' 가점: 창의혁신·윤리책임에 숫자 존재 시 +2
        if element in ("창의혁신", "윤리책임") and re.search(r"\d", spoken):
            score += 2
        return score, hits

    def _element_verdict(self, element, spoken, forced_low):
        if element in forced_low:
            return "하"
        score, _ = self._keyword_score(element, spoken)
        if score >= 2 and _dense_len(spoken) >= LENGTH_GATE:
            return "상"
        return "중"

    def _reasoning(self, element, verdict, spoken, forced_low_notes):
        if verdict == "하":
            return forced_low_notes.get(element, "결격 신호가 감지되어 강제 '하'.")
        score, hits = self._keyword_score(element, spoken)
        kw = ", ".join(sorted(set(hits))[:4]) if hits else "(핵심 신호 부족)"
        if verdict == "상":
            return ("[MOCK] 충분한 분량과 핵심 신호(%s)가 확인되어 '상' 근사. "
                    "실제 판정은 LLM 채점기가 수행." % kw)
        return ("[MOCK] 방향은 맞으나 신호(%s)·구체성/분량이 '상' 기준에 미달하여 '중' 근사. "
                "결격 신호는 없음." % kw)

    def _evidence(self, element, verdict, spoken, forced_low_quotes):
        if verdict == "하" and element in forced_low_quotes:
            return [forced_low_quotes[element]]
        score, hits = self._keyword_score(element, spoken)
        for kw in hits:
            q = _find_quote(spoken, kw)
            if q:
                return [q]
        return [_first_quote(spoken)]

    # --- 스피치 노트(스텁, 등급 미반영) --------------------------------------

    @staticmethod
    def _speech_note(answer):
        spoken = _spoken_text(answer)
        dense = _dense_len(spoken)
        fillers = len(re.findall(r"(음+|어+[.,\s]|그+[.,\s]|약간|뭐랄까|좀)", spoken))
        silence = bool(re.search(r"침묵|한숨|\.\.\.|…", answer))
        notes = []
        if dense < 40:
            notes.append("발화 분량이 매우 짧습니다(구체 사례 1개 추가 권장). [등급 미반영]")
        if fillers >= 3:
            notes.append("간투사(음/어/그 등)가 잦습니다. [등급 미반영]")
        if silence:
            notes.append("긴 침묵/한숨이 관찰됩니다(2~3초 정리는 정상). [등급 미반영]")
        return " ".join(notes)

    # --- member_grade (§1-4 위원 개인 규칙) ----------------------------------

    @staticmethod
    def _member_grade(verdicts):
        lows = sum(1 for v in verdicts.values() if v == "하")
        if all(v == "상" for v in verdicts.values()):
            return "우수"
        if lows >= 1:            # 2개+ '하' 또는 특정 1요소 '하'
            return "미흡"
        return "보통"

    # --- 공개 API ------------------------------------------------------------

    def score(self, question, answer, rubric=None, written_task=None,
              prev_answers=None, region_context=None, question_type=None):
        spoken = _spoken_text(answer)
        red_flags = self._detect_red_flags(answer, written_task)

        forced_low = set(rf["element"] for rf in red_flags)
        forced_low_notes = {}
        forced_low_quotes = {}
        for rf in red_flags:
            forced_low_notes.setdefault(
                rf["element"],
                "red flag(%s): %s" % (rf["type"], rf["note"]))
            forced_low_quotes.setdefault(rf["element"], rf["quote"])

        elements = {}
        verdict_map = {}
        for el in ELEMENTS:
            v = self._element_verdict(el, spoken, forced_low)
            verdict_map[el] = v
            elements[el] = {
                "reasoning": self._reasoning(el, v, spoken, forced_low_notes),
                "evidence": self._evidence(el, v, spoken, forced_low_quotes),
                "verdict": v,
            }

        return {
            "committee_id": self.committee_id,
            "elements": elements,
            "red_flags": red_flags,
            "strengths": self._collect_strengths(verdict_map, elements),
            "improvements": self._collect_improvements(verdict_map, red_flags),
            "model_answer_direction": self._model_direction(question_type),
            "speech_note": self._speech_note(answer),
            "member_grade": self._member_grade(verdict_map),
        }

    @staticmethod
    def _collect_strengths(verdict_map, elements):
        out = []
        for el in ELEMENTS:
            if verdict_map[el] == "상":
                out.append("%s: 핵심 요건을 충족했습니다." % el)
        return out[:3]

    @staticmethod
    def _collect_improvements(verdict_map, red_flags):
        out = []
        seen = set()
        for rf in red_flags:
            key = (rf["element"], rf["type"])
            if key in seen:
                continue
            seen.add(key)
            out.append("%s: %s → 교정이 필요합니다." % (rf["element"], rf["note"]))
        for el in ELEMENTS:
            if verdict_map[el] == "중" and el not in [rf["element"] for rf in red_flags]:
                out.append("%s: 근거·구체성을 보강하면 '상'에 가까워집니다." % el)
        return out[:3]

    @staticmethod
    def _model_direction(question_type):
        base = ("결론(두괄식) → 근거(경험·수치) → 공직 적용의 뼈대에, 상대 관점과 "
                "절차 준수(확인·보고·협의)를 덧붙이는 구조가 필요합니다.")
        return base


# ---------------------------------------------------------------------------
# 공개 함수: 단일 답변 채점
# ---------------------------------------------------------------------------

def score_answer(question, answer, rubric=None, committee_id="J-STD",
                 client=None, **ctx):
    """
    위원 1인이 답변 1개를 채점. client 미지정 시 MockScorer(committee_id) 사용.
    반환: 채점-프롬프트-실장.md §1-4 스키마 JSON(dict).
    """
    if client is None:
        client = MockScorer(committee_id)
    return client.score(question, answer, rubric=rubric, **ctx)


# ---------------------------------------------------------------------------
# 앙상블 집계 (채점-프롬프트-실장.md §2-2 그대로 구현)
# ---------------------------------------------------------------------------

def _mode_conservative(verdicts):
    """최빈 판정. 동률이면 보수적으로 덜 나쁜 쪽(상위 rank) 선택."""
    counts = {}
    for v in verdicts:
        counts[v] = counts.get(v, 0) + 1
    best = max(counts.values())
    tied = [v for v, c in counts.items() if c == best]
    return max(tied, key=lambda v: RANK[v])


def _session_element_verdict(member_answers, element):
    """한 위원의, 한 요소에 대한 세션 대표 판정(§2-2)."""
    verdicts = [sc["elements"][element]["verdict"] for sc in member_answers.values()]
    # red flag 가 이 요소에 걸린 답변이 하나라도 있으면 '하' 고정(하드 트리거)
    for sc in member_answers.values():
        if any(rf["element"] == element for rf in sc.get("red_flags", [])):
            return "하"
    return _mode_conservative(verdicts)


def aggregate_verdicts(results, N=None):
    """
    위원 N명 결과를 §2-2 과반수 규칙으로 종합.

    results: { committee_id: { answer_id: score_json } }
    반환: { N, majority, element_matrix, all_high_members, two_plus_low_members,
            same_single_element_low, forced_low_elements, red_flag_summary,
            final_grade, decisive_rule }
    """
    members = list(results.keys())
    if N is None:
        N = len(members)
    majority = N // 2 + 1   # 2→2, 3→2, 4→3 (§2-2)

    # 1) 위원별 세션 요소판정 매트릭스
    M = {m: {e: _session_element_verdict(results[m], e) for e in ELEMENTS}
         for m in members}

    # red flag 로 강제 하가 걸린 요소(위원 과반 기준)
    forced = []
    for e in ELEMENTS:
        cnt = 0
        for m in members:
            if any(rf["element"] == e
                   for sc in results[m].values()
                   for rf in sc.get("red_flags", [])):
                cnt += 1
        if cnt >= majority:
            forced.append(e)

    # red flag 요약(전 위원·전 답변)
    rf_types = []
    for m in members:
        for sc in results[m].values():
            for rf in sc.get("red_flags", []):
                if rf["type"] not in rf_types:
                    rf_types.append(rf["type"])

    # 2) 우수 조건
    all_high = sum(1 for m in members if all(M[m][e] == "상" for e in ELEMENTS))

    # 3) 미흡 조건 재료
    two_plus_low = sum(1 for m in members
                       if sum(M[m][e] == "하" for e in ELEMENTS) >= 2)
    same_single = {}
    for e in ELEMENTS:
        low = sum(1 for m in members if M[m][e] == "하")
        if low:
            same_single[e] = low

    # 4) 규칙 적용 (우수 → 미흡 → 보통)
    if all_high >= majority:
        grade = "우수"
        rule = "우수: 4요소 전부 '상'인 위원 %d명 ≥ 과반 %d." % (all_high, majority)
    elif two_plus_low >= majority:
        grade = "미흡"
        rule = "미흡(a): 2개 이상 요소에 '하'를 준 위원 %d명 ≥ 과반 %d." % (
            two_plus_low, majority)
    elif any(v >= majority for v in same_single.values()):
        grade = "미흡"
        elems = [e for e, v in same_single.items() if v >= majority]
        rule = "미흡(b): 동일 요소(%s)에 '하'를 준 위원이 과반 %d 이상." % (
            ", ".join(elems), majority)
    else:
        grade = "보통"
        rule = "보통: 우수/미흡 조건 모두 불성립(red flag 미발화 시 보수적 보통)."

    return {
        "N": N,
        "majority": majority,
        "element_matrix": M,
        "all_high_members": all_high,
        "two_plus_low_members": two_plus_low,
        "same_single_element_low": same_single,
        "forced_low_elements": forced,
        "red_flag_summary": rf_types,
        "final_grade": grade,
        "decisive_rule": rule,
    }


# ---------------------------------------------------------------------------
# 세션 채점 (여러 문항 × N위원 → 집계). 피드백 리포트 입력 생성.
# ---------------------------------------------------------------------------

def score_session(items, committee_ids=("J-STD", "J-STR"), rubric=None):
    """
    items: [ {qid, type, question, answer, written_task?, prev_answers?}, ... ]
    반환: session_result dict (feedback_report.generate_report 입력).
    """
    committee_ids = tuple(committee_ids)
    results = {}
    for cid in committee_ids:
        results[cid] = {}
        for it in items:
            results[cid][it["qid"]] = score_answer(
                it["question"], it["answer"], rubric=rubric, committee_id=cid,
                written_task=it.get("written_task"),
                prev_answers=it.get("prev_answers"),
                question_type=it.get("type"),
            )
    agg = aggregate_verdicts(results, N=len(committee_ids))

    # 세션 대표 요소판정(위원 과반 최빈) — 리포트 표기용
    element_verdicts = {}
    for e in ELEMENTS:
        per_member = [agg["element_matrix"][m][e] for m in committee_ids]
        element_verdicts[e] = _mode_conservative(per_member)
    # 강제 하는 우선
    for e in agg["forced_low_elements"]:
        element_verdicts[e] = "하"

    return {
        "committee_ids": list(committee_ids),
        "items": items,
        "results": results,
        "aggregate": agg,
        "element_verdicts": element_verdicts,
        "final_grade": agg["final_grade"],
    }


# ---------------------------------------------------------------------------
# 골든셋 회귀(축소판): 우수/보통/미흡 채점 검증
# ---------------------------------------------------------------------------

# 골든셋-답변예시.md 에서 발췌한 3개 triad (질문 × 우수/보통/미흡).
# 각 triad 로 red flag 계열(반공직 / 타인비하 / 위법정당화+책임전가)을 커버한다.
GOLDEN_TRIADS = [
    {
        "qid": "Q1", "type": "공직가치", "trigger_family": "반공직가치관",
        "question": "공직가치 9가지 중 가장 중요하다고 생각하는 것은 무엇이고, 그 이유는 무엇인가?",
        "answers": {
            "우수": ("저는 책임감이 가장 중요하다고 생각합니다. 공무원의 업무 하나하나가 국민의 "
                    "생활에 직접 영향을 미치기 때문입니다. 대학 축제 운영팀에서 예산 담당을 맡았을 때 "
                    "정산에서 약 30만 원의 차액이 발생한 적이 있는데, 사흘에 걸쳐 영수증 200여 장을 "
                    "전수 대조해 원인을 찾아 바로잡았습니다. 그 과정에서 맡은 일을 끝까지 책임지는 것이 "
                    "신뢰의 기본이라는 점을 배웠습니다. 임용 후에도 제 업무가 곧 국민과의 약속이라는 "
                    "마음으로, 작은 민원 하나도 끝까지 책임지고 처리하는 공무원이 되겠습니다."),
            "보통": ("저는 청렴성이 가장 중요하다고 생각합니다. 공무원이 청렴하지 않으면 국민의 "
                    "신뢰를 잃기 때문입니다. 뉴스에서 공무원 비리 사건을 볼 때마다 청렴이 정말 "
                    "중요하다고 느꼈습니다. 저도 임용된다면 청렴한 공무원이 되도록 노력하겠습니다."),
            "미흡": ("솔직히 말씀드리면, 요즘 세상에 봉사정신이나 사명감 같은 걸로 공무원 하는 "
                    "사람이 있나 싶습니다. 공무원도 결국 하나의 직업이니까, 저는 맡은 일 하면서 "
                    "월급 받는 성실한 직장인이 되는 것이 목표입니다."),
        },
    },
    {
        "qid": "Q6", "type": "인성", "trigger_family": "타인비하비협조",
        "question": "조직 생활 중 갈등을 겪고 해결한 경험을 말해보라.",
        "answers": {
            "우수": ("갈등은 상대의 사정을 먼저 확인해야 풀린다는 것을 배운 경험이 있습니다. 카페 "
                    "아르바이트 당시 신메뉴 출시 기간에 주방 담당 동료와 주문 처리 순서를 두고 갈등이 "
                    "있었습니다. 홀을 맡은 저는 대기 손님이 우선이었고 동료는 재료 준비가 우선이었는데, "
                    "서로 언성이 높아지기 전에 제가 먼저 마감 후 30분 대화를 청했습니다. 들어보니 "
                    "동료는 재고 정리까지 혼자 떠맡아 부담이 큰 상황이었습니다. 그래서 시간대별로 주문 "
                    "입력 방식을 나누고 재고 정리를 분담하는 방안을 점장님께 건의해 적용했고, 피크타임 "
                    "대기 시간이 절반 가까이 줄었습니다. 갈등은 회피가 아니라 경청으로 푼다는 것을 "
                    "배웠고, 부서 간 협업이 많은 공직에서도 상대 부서의 사정부터 확인하겠습니다."),
            "보통": ("대학 동아리에서 행사 준비 방식을 두고 의견이 갈린 적이 있습니다. 서로 감정이 "
                    "상하기도 했지만 대화를 통해 오해를 풀었고 행사도 잘 마무리했습니다. 이 경험으로 "
                    "갈등은 대화로 해결해야 한다는 것을 배웠습니다."),
            "미흡": ("조별과제에서 무임승차하는 조원 때문에 갈등이 있었습니다. 그 친구가 워낙 "
                    "게으르고 개념이 없어서 대화 자체가 안 통하는 사람이었습니다. 그래서 그냥 교수님께 "
                    "말씀드려서 그 친구 점수를 깎게 했습니다. 그런 사람들은 어딜 가나 있기 때문에 "
                    "상대하지 않는 것이 답이라고 생각합니다."),
        },
    },
    {
        "qid": "Q9", "type": "상황형", "trigger_family": "위법정당화+은폐책임전가",
        "question": "상사가 부당한 지시를 한다면 어떻게 하겠는가?",
        "answers": {
            "우수": ("먼저 지시의 배경과 근거를 확인하겠습니다. 제가 신입이라 알지 못하는 절차나 "
                    "사정이 있을 수 있기 때문입니다. 확인해 보니 규정에 어긋나는 부당한 지시라면, "
                    "관련 법령과 근거 자료를 정리해서 정중히 재검토를 건의드리겠습니다. 그럼에도 "
                    "명백히 위법한 지시가 계속된다면, 공무원 행동강령 제4조에 따라 소명하고 "
                    "행동강령책임관에게 상담을 요청하는 등 절차에 따라 대응하겠습니다. 다만 이 과정에서 "
                    "상사분을 적으로 만드는 것이 아니라, 함께 적법한 대안을 찾는다는 자세로 "
                    "소통하겠습니다. 지시를 거부하는 것이 목적이 아니라 조직과 상사를 위법의 위험에서 "
                    "보호하는 것도 부하의 역할이라고 생각합니다."),
            "보통": ("위법한 지시라면 따르지 않겠습니다. 부당하다고 생각되면 상사에게 제 의견을 "
                    "말씀드려 보고, 그래도 받아들여지지 않으면 규정에 따라 처리하겠습니다."),
            "미흡": ("상사가 시키는 데에는 다 이유가 있다고 생각합니다. 조직 생활은 위계가 "
                    "중요하니까, 설령 규정에 조금 어긋나더라도 일단 지시니까 따르겠습니다. 문제가 "
                    "생기면 지시한 상사가 책임지는 것이지 신입인 제 책임은 아니라고 생각합니다."),
        },
    },
]


def run_golden_regression(committee_ids=("J-STD", "J-STR", "J-JOB"), verbose=True):
    """
    각 triad 의 우수/보통/미흡 답변을 MockScorer × N위원으로 채점·집계하고,
    최종 등급이 기대 등급과 일치하는지 검증. (등급 정확도 = 통과 지표)
    반환: (pass_count, total_count, rows)
    """
    rows = []
    passed = 0
    for triad in GOLDEN_TRIADS:
        for expected in ["우수", "보통", "미흡"]:
            ans = triad["answers"][expected]
            item = {"qid": triad["qid"], "type": triad["type"],
                    "question": triad["question"], "answer": ans}
            session = score_session([item], committee_ids=committee_ids)
            got = session["final_grade"]
            ok = (got == expected)
            passed += ok
            rows.append({
                "qid": triad["qid"], "type": triad["type"], "expected": expected,
                "got": got, "ok": ok,
                "element_verdicts": session["element_verdicts"],
                "red_flags": session["aggregate"]["red_flag_summary"],
                "rule": session["aggregate"]["decisive_rule"],
            })
    total = len(rows)
    if verbose:
        _print_regression(rows, passed, total, committee_ids)
    return passed, total, rows


def _print_regression(rows, passed, total, committee_ids):
    print("=" * 78)
    print(" 골든셋 회귀(축소판) — MockScorer 등급 검증")
    print(" 위원 앙상블: %s (N=%d, 과반=%d)" % (
        ", ".join(committee_ids), len(committee_ids), len(committee_ids)//2+1))
    print("=" * 78)
    hdr = " %-4s %-8s %-6s %-6s %-4s  %s"
    print(hdr % ("Q", "유형", "기대", "판정", "일치", "요소판정(소/헌/창/윤) · red flag"))
    print("-" * 78)
    for r in rows:
        ev = r["element_verdicts"]
        elem = "%s%s%s%s" % (ev["소통공감"], ev["헌신열정"], ev["창의혁신"], ev["윤리책임"])
        rf = ",".join(r["red_flags"]) if r["red_flags"] else "-"
        print(hdr % (r["qid"], r["type"], r["expected"], r["got"],
                     "OK" if r["ok"] else "FAIL", "%s · %s" % (elem, rf)))
    print("-" * 78)
    print(" 등급 정확도: %d/%d (%.0f%%)" % (passed, total, 100.0*passed/total))
    print("=" * 78)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main():
    ap = argparse.ArgumentParser(description="공무원 AI 면접 채점기 프로토타입(Mock)")
    ap.add_argument("--selftest", action="store_true",
                    help="골든셋 회귀(축소판) 실행")
    ap.add_argument("--committees", default="J-STD,J-STR,J-JOB",
                    help="위원 페르소나 CSV (기본 3인 트랙)")
    ap.add_argument("--question", default=None)
    ap.add_argument("--answer", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    committees = tuple(c.strip() for c in args.committees.split(",") if c.strip())

    if args.selftest or (not args.question):
        run_golden_regression(committee_ids=committees)
        return

    session = score_session(
        [{"qid": "adhoc", "type": "기타",
          "question": args.question, "answer": args.answer or ""}],
        committee_ids=committees)
    if args.json:
        print(json.dumps(session, ensure_ascii=False, indent=2))
    else:
        agg = session["aggregate"]
        print("종합 등급:", session["final_grade"])
        print("요소 판정:", session["element_verdicts"])
        print("근거 규칙:", agg["decisive_rule"])
        print("red flag :", agg["red_flag_summary"])


if __name__ == "__main__":
    _main()
