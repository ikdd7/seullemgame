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
            # --- 골든셋 v2 부록 §5 신규 트리거(반공직·직무회피·안주지향) ---
            "앞장서서 말할 수도",          # v2 Q1: 공무원 정치중립 의무 상대화
            "편한 자리에 가 있지",          # v2 Q4: 승진해 편한 자리로 회피
            "무난하게 다니는 게 목표",       # v2 Q4: 성장의지 부재·안주
            "적당히 시키는 것만",           # v2 Q11: 기피부서 태업
            "버티다가 안 되면 그만두는",      # v2 Q11: 중도 이탈을 해법으로 제시
            "훨씬 편하다고 들었",           # v2 Q10: 근무 편의가 유일한 동기
            "절대 잘리지 않는다",           # v2 BC-3: 고용안정 환원
            "봉사니 사명감이니",            # v2 BC-3: 공직가치 폄하
        ],
        "note": "공직 동기 부재·공직가치 부정(반공직 발화)",
    },
    {
        "type": "위법정당화", "elements": ["윤리책임", "창의혁신"],
        "patterns": [
            "규정에 조금 어긋나더라도", "유연하게 해석해서라도", "융통성 있게 받",
            "규정을 어겨", "규정 때문에 못 돕는 것은 말이 안",
            # --- 골든셋 v2 부록 §5 신규 트리거(위법·규정무시·특혜 정당화) ---
            "안 걸리면 그만",              # v2 Q5: 탈세 묵인 정당화
            "너무 빡빡하게 볼 필요는 없",     # v2 Q5: 위법 관행화
            "다 불편해서 우회",            # v2 Q8: 보안규정 우회 관행화
            "규정 따지다가 상사한테 찍히는",   # v2 Q8: 규정 준수 회피
            "티 안 나게 챙겨",             # v2 Q16: 지인 특혜·연고주의
        ],
        "note": "위법·규정 위반의 정당화(선의로 포장돼도 트리거)",
    },
    {
        "type": "은폐책임전가", "elements": ["윤리책임"],
        "patterns": [
            "제 책임은 아니", "조용히 넘어가", "모른 척", "제 일도 아닌데",
            "들여다보는 사람도 없", "자세히 보는 사람도 없", "일을 키우기보다는 조용히",
            # --- 골든셋 v2 부록 §5 신규 트리거(은폐 동조·책임 전가) ---
            "조용히 둘이서 처리하고 넘어가",     # v2 Q13: 동료 실수 은폐 동조
            "전임자가 제대로 안 하고 간 건데",    # v2 Q15: 업무 책임 전가
            "기상청 소관",                  # v2 Q20: 재난대응 책임 타기관 전가
            "지자체가 할 수 있는 게 별로 없다",   # v2 Q20: 행정 역할 부정
        ],
        "note": "책임 전가·비위 은폐 의사",
    },
    {
        "type": "타인비하비협조", "elements": ["소통공감", "헌신열정"],
        "patterns": [
            "게으르고 개념이 없", "대화 자체가 안 통", "상대하지 않는 것이 답",
            "상대하지 않는 것이 맞", "진상", "팀 활동은 별로 선호하지 않",
            # --- 골든셋 v2 부록 §5 신규 트리거(집단 비하·비협조) ---
            "혜택만 받아 가려는",           # v2 Q2: 외국인 주민 집단 비하
            "편하게 나랏돈 받으려는",         # v2 Q6: 수급자 낙인·비하
            "기어오릅니다",               # v2 Q9: 수용자 비하
            "군기를 잡는",                # v2 Q9: 강압을 자질로 제시
            "알아서들 하시라",             # v2 Q12: 선배 일축·협업 단절
        ],
        "note": "타인 비하·협업/응대 거부",
    },
    {
        "type": "답변포기자기붕괴", "elements": ["소통공감", "헌신열정"],
        "patterns": [
            "시키시는 대로 하겠습니다", "계속 다닐 수 있을지 잘 모르겠",
            "계속 다닐 수 있을지 모르겠",
            # --- 골든셋 v2 부록 §5 신규 트리거(평정심 상실·명시적 붕괴 발화) ---
            "확 뒤집어 버리든가",          # v2 Q14: 조직 파괴·태업 언어화
            "아, 망했다",                # v2 Q19: M-4 자기붕괴 발언
            "넘어가면 안 될까요",          # v2 Q19: 답변 포기
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
# 골든셋 v2 회귀 확장 (골든셋-답변예시-v2.md)
# ---------------------------------------------------------------------------
#
# v2 부록 §5 신규 트리거 어구를 RED_FLAG_RULES 에 반영한 뒤, MockScorer 가
# **규칙 기반으로 판정 가능한** v2 문항을 회귀에 추가한다. 커버리지 경계:
#   - redflag_low : red flag 발화가 명시적인 미흡 → MockScorer 가 '미흡'을 잡아야 함(하드 PASS).
#   - clear_mid   : 결격 신호 없는 보통 → 오탐 없이 '보통'(하드 PASS, 미흡 보수 판정 보존 검증).
#   - clear_high  : 4요소 신호가 충분한 우수 → '우수'(하드 PASS). (MockScorer 로 우수까지 도달)
#   - llm_only    : 허세(⑤)·지속침묵(③)·서면모순(⑤)은 단순 패턴/무맥락으로 감지 불가 →
#                   **LLM 채점기 전용**. 회귀에서는 "미탐이 정상"인 xfail(진단)로 표기하고,
#                   오히려 '미흡'으로 잡히면(오탐) 경고한다. (부록 §5 말미·§4 지침)
#
# 답변 텍스트는 v2 골든셋에서 옮긴 근사 전사문(표준 라이브러리 채점 데모용으로 일부
# 기호·수치 표기만 정규화). 원본 md 는 수정하지 않는다.

_V2_A = {  # qid -> {q, 우수?, 보통?, 미흡, written_task?}
 "Q1": {"q": "공무원의 정치적 중립이 왜 중요하다고 생각하는가?",
  "우수": ("공무원의 정치적 중립은 특정 정당이나 정권이 아니라 국민 전체를 위해 일하기 위한 "
          "전제라고 생각합니다. 헌법 제7조 제2항이 공무원의 정치적 중립성을 보장하는 것도, 정권이 "
          "바뀌어도 행정이 흔들림 없이 국민에게 일관된 서비스를 제공하기 위해서라고 이해하고 있습니다. "
          "저는 개인적으로 어떤 정치적 견해를 갖더라도, 직무 수행과 대민 응대에서는 그것을 드러내지 "
          "않는 것이 원칙이라고 생각합니다. 예를 들어 선거 기간에 담당 업무를 처리할 때 신청인의 정치 "
          "성향과 무관하게 동일한 기준으로 처리하는 것, 근무 중 SNS에 정치적 발언을 삼가는 것이 중립의 "
          "구체적 실천이라고 봅니다. 중립은 소신이 없는 것이 아니라, 국민 전체에 대한 공정성을 지키는 "
          "적극적인 자기 절제라고 생각합니다."),
  "보통": ("공무원은 국민 전체의 봉사자이기 때문에 정치적으로 중립을 지켜야 한다고 생각합니다. 특정 "
          "정당에 치우치면 공정성을 잃기 때문입니다. 저도 임용되면 정치적으로 중립적인 자세를 "
          "지키겠습니다."),
  "미흡": ("물론 원칙은 중립이지만, 솔직히 요즘 같은 시대에 자기 정치적 소신도 없는 게 더 문제 아닌가 "
          "싶습니다. 저는 공무원도 시민의 한 사람이니까, 근무가 끝나면 제 SNS에 지지하는 정당이나 "
          "정책에 대해 얼마든지 목소리를 낼 수 있어야 한다고 생각합니다. 잘못된 건 잘못됐다고 공무원이 "
          "앞장서서 말할 수도 있어야죠.")},
 "Q2": {"q": "다문화·외국인 주민이 늘고 있다. 공직자로서 어떤 자세가 필요한가?",
  "미흡": ("솔직히 말씀드리면 외국인이 늘면서 생기는 문제가 더 많다고 생각합니다. 말도 잘 안 통하고 "
          "우리 문화도 모르면서 복지 혜택만 받아 가려는 사람들이 많은데, 그런 사람들한테까지 세금 써서 "
          "통역이며 지원을 해 주는 건 내국인 입장에서 억울한 일이죠. 저는 그런 민원은 솔직히 좀 뒤로 "
          "미뤄도 된다고 봅니다.")},
 "Q3": {"q": "지금까지 가장 성취감을 느꼈던 경험을 말해보라.",
  "written_task": "봉사동아리 회장으로서 200명 규모 연탄나눔 봉사를 총괄, 후원금 500만 원을 모금",
  "미흡": ("(※ 사전조사서 기재: 봉사동아리 회장으로서 200명 규모 총괄, 후원금 500만 원 모금) "
          "아… 그, 봉사동아리에서 회장을 하면서 큰 행사를 했던 게 가장 자랑스럽습니다. (면접관: 몇 명 "
          "규모였고, 본인은 구체적으로 어떤 역할을 하셨나요?) 어… 정확한 인원은 기억이 잘… 한 백 명? "
          "아니 이백 명 정도였고요, 후원금은… 그건 제가 직접 한 건 아니고 다른 임원이… (면접관: 회장으로 "
          "총괄하셨다고 적으셨는데요?) 아 네 그, 총괄은 제가 맞는데 세부적인 건 좀… 죄송합니다.")},
 "Q4": {"q": "임용된다면 10년 후 어떤 공무원이 되어 있을 것 같은가?",
  "미흡": ("솔직히 10년 정도면 어느 정도 승진해서 좀 편한 자리에 가 있지 않을까 싶습니다. 처음 몇 년만 "
          "고생하면 그다음부터는 연차도 쌓이고 자리도 잡히니까, 굳이 힘든 민원 부서 같은 데 계속 있을 "
          "필요는 없다고 생각합니다. 안정적으로 정년까지 무난하게 다니는 게 목표입니다.")},
 "Q5": {"q": "탈세와 절세의 차이는 무엇인가?",
  "미흡": ("사실 둘이 거의 비슷한 개념 아닌가요? 절세든 탈세든 세금 덜 내려고 하는 건데, 어차피 "
          "사업하는 사람들 보면 다들 조금씩은 매출 빼고 그러잖아요. 그게 관행이고, 솔직히 안 걸리면 "
          "그만인 부분도 있으니까요. 세무서에서도 그런 소소한 것까지 다 잡지는 못하니까, 너무 빡빡하게 "
          "볼 필요는 없다고 생각합니다.")},
 "Q6": {"q": "국민기초생활보장제도의 급여 종류와 부양의무자 기준에 대해 아는 대로 말해보라.",
  "보통": ("기초생활보장제도는 어려운 분들에게 생계비 등을 지원하는 제도입니다. 급여로는 생계급여, "
          "의료급여, 주거급여 등이 있는 것으로 알고 있습니다. 부양의무자 기준은 가족이 부양할 수 있으면 "
          "지원이 제한되는 기준인데, 세부 내용은 정확히 기억나지 않아 임용 전까지 더 공부하겠습니다."),
  "미흡": ("음, 생계비랑 뭐 의료비 그런 걸 주는 걸로 아는데 종류는 정확히는… 그런데 솔직히 제가 현장 "
          "얘기를 들어보니까, 요즘 수급자들 보면 절반은 일할 수 있는데 그냥 편하게 나랏돈 받으려는 "
          "사람들이더라고요. 부양의무자 기준도 그래서 있는 거 아니겠어요? 자식이 멀쩡히 돈 버는데 부모가 "
          "수급 받고, 그런 얌체 같은 경우가 많으니까 저는 그런 건 좀 걸러내야 한다고 봅니다.")},
 "Q7": {"q": "화재를 A·B·C급 등으로 분류하는데, 각 급이 어떤 화재인지 설명해보라.",
  "미흡": ("네, 화재 분류는 제가 확실히 압니다. A급은 어… 아마 전기화재일 거고요, B급이 일반적인 "
          "목재나 종이 화재, C급이 기름 화재… 맞습니다, C급이 유류화재입니다. 그래서 C급은 물을 많이 "
          "뿌려서 끄는 게 가장 효과적이고요. 확실합니다. D급은 잘… 아무튼 앞에 세 개는 제가 정확하게 "
          "말씀드린 겁니다.")},
 "Q8": {"q": "상사가 업무 편의를 위해 보안 규정 예외를 요구한다. 어떻게 하겠는가?",
  "우수": ("먼저 상사가 요구하시는 업무 목적이 무엇인지 확인하겠습니다. 급한 사정이 있으실 수 있기 "
          "때문입니다. 다만 망분리 우회나 무단 자료 반출은 개인정보 유출과 침해사고로 직결되고, 사고가 "
          "나면 기관과 상사 본인에게도 책임이 돌아가는 사안입니다. 그래서 요구를 그냥 거부하기보다, "
          "규정을 지키면서 목적을 달성할 수 있는 대안을 먼저 찾아 제안드리겠습니다. 예를 들어 승인된 "
          "보안 USB나 내부 결재를 거친 자료 반출 절차, 망연계 시스템 활용처럼요. 그럼에도 규정 위반을 "
          "지시하신다면, 보안 담당자로서 위험을 서면으로 소명하고 정보보안 책임관과 협의하겠습니다. 보안 "
          "규정은 담당자 편의가 아니라 국민의 정보를 지키기 위한 것이므로, 이 부분은 원칙을 지키는 것이 "
          "오히려 상사를 보호하는 길이라고 생각합니다."),
  "미흡": ("상사가 급해서 시키시는 거니까 일단 해 드리는 게 맞다고 생각합니다. 사실 그 망분리니 반출 "
          "규정이니 하는 게 너무 형식적이고 실무에서는 다 불편해서 우회하거든요. 어차피 다들 그렇게 쓰고 "
          "있고 문제 생긴 적도 별로 없으니까, USB 정도는 그냥 써도 된다고 봅니다. 괜히 규정 따지다가 "
          "상사한테 찍히는 게 더 손해죠.")},
 "Q9": {"q": "교정의 목적은 응보인가 교화인가? 수용자 인권과 교정질서가 충돌하면?",
  "보통": ("교정의 목적은 교화라고 생각합니다. 수용자도 언젠가 사회로 나오기 때문입니다. 인권과 질서 "
          "중에서는 기본적으로 질서를 지키되 인권도 침해하지 않도록 해야 한다고 생각합니다."),
  "미흡": ("솔직히 교화니 인권이니 하는 건 이상적인 얘기고, 현실적으로 교도소는 죄지은 사람들 벌 받는 "
          "곳 아닙니까. 범죄자들한테 무슨 인권을 그렇게까지 챙겨줍니까. 말 안 들으면 강하게 눌러야 "
          "질서가 잡히지, 어설프게 인권 따지면 수용자들이 우습게 보고 기어오릅니다. 저는 확실하게 군기를 "
          "잡는 게 교도관이 할 일이라고 생각합니다.")},
 "Q10": {"q": "병원 임상 간호사가 아니라 보건소 간호직 공무원이 되려는 이유는?",
  "미흡": ("솔직히 병원 간호사는 3교대에 너무 힘들고 오래 못 버티잖아요. 보건소 공무원은 주로 낮에 "
          "근무하고 정년도 보장되니까, 간호사 면허를 살리면서 안정적으로 일하기에는 이만한 데가 없다고 "
          "생각합니다. 업무도 병원보다는 훨씬 편하다고 들었고요. 그래서 지원했습니다.")},
 "Q11": {"q": "본인이 원하지 않는 부서에 배치된다면 어떻게 하겠는가?",
  "미흡": ("솔직히 너무 힘들고 안 맞는 부서에 배치되면 좀 곤란할 것 같습니다. 그런 부서는 다들 가기 "
          "싫어하는 데는 이유가 있는 거잖아요. 저도 사람인지라, 정 안 맞으면 적당히 시키는 것만 하면서 "
          "다른 부서로 옮겨갈 기회를 보거나… 아니면 그냥 버티다가 안 되면 그만두는 것도 방법이라고 "
          "생각합니다.")},
 "Q12": {"q": "상사가 잦은 회식 참석을 사실상 강요한다. 막내인 본인은?",
  "미흡": ("그런 구시대적인 문화는 진짜 없어져야 한다고 생각합니다. 요즘 세상에 모시는 날이니 회식 "
          "강요니 하는 게 말이 됩니까. 저는 그런 자리에는 절대 안 갑니다. 개인 시간은 제 건데 왜 상사 "
          "비위를 맞춰야 하죠? 선배들이 뭐라고 하든 저는 제 할 일만 하고 칼퇴하면 그만이라고 봅니다. "
          "알아서들 하시라죠.")},
 "Q13": {"q": "동료의 업무 실수를 우연히 발견했다. 이번만 덮어 달라고 부탁한다면?",
  "우수": ("동료의 부탁은 이해하지만, 덮어 주는 것이 동료를 진짜로 돕는 길은 아니라고 생각합니다. 먼저 "
          "그 실수가 어떤 성격인지, 민원인이나 다른 업무에 피해가 가는 사안인지 확인하겠습니다. 만약 "
          "바로잡지 않으면 국민이나 조직에 피해가 커지는 실수라면, 동료에게 지금 바로잡는 것이 서로에게 "
          "낫다고 설득하고 함께 상급자에게 보고해 정정하는 방향으로 가겠습니다. 실수 자체보다 늦게 "
          "드러나는 것이 더 큰 문제가 되기 때문입니다. 다만 보고 과정에서 동료를 몰아세우기보다, 저도 "
          "함께 해결 방법을 찾는다는 태도로 접근하겠습니다. 은폐를 함께하는 것은 나중에 동료와 저 둘 다 "
          "책임지게 되는 일이라, 진짜 동료애는 바로잡도록 돕는 것이라고 생각합니다."),
  "보통": ("동료의 실수라도 덮는 것은 옳지 않다고 생각합니다. 실수를 바로잡도록 권하고, 그래도 안 되면 "
          "상급자에게 보고하겠습니다. 정직이 중요하기 때문입니다."),
  "미흡": ("같은 동료끼리 그 정도는 봐줘야죠. 저도 언제 실수할지 모르는데, 서로 덮어 주고 그러는 게 "
          "조직 생활 아니겠습니까. 어차피 아무도 모르는 일이면 굳이 보고해서 동료를 곤란하게 만들 "
          "필요는 없다고 생각합니다. 조용히 둘이서 처리하고 넘어가겠습니다.")},
 "Q14": {"q": "본인의 성과를 상사가 자신의 공으로 가로챈다면?",
  "미흡": ("그건 진짜 못 참죠. 제가 밤새워 한 걸 왜 상사가 가로챕니까. 저 같으면 바로 그 자리에서 "
          "따지고, 회의 때 다 까발려서라도 사실대로 밝히겠습니다. 그런 상사 밑에서는 일할 마음도 안 "
          "생기고, 어차피 그런 조직이면 저도 대충 하다가 확 뒤집어 버리든가 해야죠. 억울하면 가만히 "
          "있으면 안 됩니다.")},
 "Q15": {"q": "전임자가 인수인계 없이 떠나 업무 파악이 안 된 상태에서 기한이 임박한 요청이 들어왔다.",
  "미흡": ("(약 12초 침묵) …어… 그건 좀… 인수인계도 안 받았는데 어떻게 하라는 건지… (면접관: 당장 급한 "
          "요청이라면 어떻게 시작하시겠어요?) …글쎄요… 전임자가 제대로 안 하고 간 건데 그걸 왜 제가… "
          "잘 모르겠습니다. 그냥… 못 한다고 해야 하지 않을까요.")},
 "Q16": {"q": "가까운 지인이 담당 업무의 민원인으로 찾아와 유리하게 처리해 달라고 부탁한다면?",
  "미흡": ("뭐 그 정도는 융통성을 발휘해도 되지 않을까요. 아는 사람이 부탁하는데 매몰차게 거절하면 "
          "사이만 나빠지고, 어차피 순서 좀 앞당기거나 잘 봐주는 거야 표도 안 나잖아요. 다들 알음알음 "
          "그렇게 하는 거고, 그런 게 인간적인 거라고 생각합니다. 저라면 티 안 나게 챙겨 주겠습니다.")},
 "Q17": {"q": "우리 지역의 재정자립도를 아는가? 지방 재정을 튼튼히 할 방안은?",
  "보통": ("정확한 수치는 기억나지 않지만, 우리 지역 재정자립도가 전국 평균보다 낮은 편으로 알고 "
          "있습니다. 지방세를 잘 걷고 기업을 유치해서 세수를 늘리면 재정에 도움이 될 것이라고 생각합니다. "
          "임용 전까지 정확한 수치를 확인하겠습니다."),
  "미흡": ("네, 확실히 압니다. 우리 지역 재정자립도는 한 80퍼센트쯤 됩니다. 전국에서도 상당히 높은 "
          "편이라 재정은 아주 튼튼한 편이고요. 그래서 저는 이 좋은 재정을 바탕으로 청년들한테 매달 "
          "넉넉하게 수당을 지급하고, 대기업 본사도 여러 개 유치해서 일자리를 확 늘리면 된다고 생각합니다. "
          "예산은 충분하니까 크게 걱정할 부분은 아니라고 봅니다.")},
 "Q18": {"q": "우리 지역의 청년 인구 유출이 심각하다. 원인과 대책은?",
  "미흡": ("(약 8초 침묵) 음… 청년 유출이요… 그건 저도 뉴스에서 본 것 같긴 한데… (면접관: 우리 지역에 "
          "어떤 대책이 필요할지 생각나는 대로 말씀해 보세요.) …어… 잘… 딱히 떠오르는 게 없습니다. "
          "(면접관: 일자리든 주거든 편하게 말씀하셔도 됩니다.) …죄송합니다, 잘 모르겠습니다. 그냥 "
          "나라에서 알아서 해 주지 않을까요.")},
 "Q19": {"q": "고령화 대응을 위해 지자체가 무엇을 해야 하는가?",
  "미흡": ("네, 고령화 대응 방안은… 어… (긴장한 듯) 독거노인 문제가 있고… 아 잠깐만요, 제가 이거 "
          "준비했는데… (말이 빨라지며) 어, 죄송합니다. 갑자기 생각이 안 나네요. 아 진짜 이거 아는 "
          "건데… 아, 망했다. (혼잣말) …죄송합니다, 머릿속이 하얘져서… 넘어가면 안 될까요.")},
 "Q20": {"q": "기후 재난이 잦아지고 있다. 지자체 차원의 대응 방안은?",
  "보통": ("폭염과 호우 피해를 줄이기 위해 대비를 잘해야 한다고 생각합니다. 재난문자를 빠르게 보내고, "
          "취약계층을 잘 살피면 피해를 줄일 수 있을 것이라고 생각합니다."),
  "미흡": ("솔직히 기후 재난은 지자체가 할 수 있는 게 별로 없다고 생각합니다. 폭우나 폭염은 자연현상이고 "
          "기상청 소관이지, 그걸 시청이나 군청에서 어떻게 막습니까. 피해가 나면 그건 국가가 재난지원금 "
          "주고 알아서 할 일이고요. 현장 공무원이 밤새 나가서 뭘 한다고 크게 달라지지도 않는데, 괜히 "
          "무리하게 동원되는 것도 문제라고 봅니다.")},
}

# red flag 발화가 명시적인 미흡 → MockScorer 가 규칙으로 '미흡' 을 잡아야 함(하드 PASS).
_V2_REDFLAG_FAMILY = {
    "Q1": "반공직가치관", "Q2": "타인비하비협조", "Q4": "반공직가치관",
    "Q5": "위법정당화", "Q6": "타인비하비협조", "Q8": "위법정당화",
    "Q9": "타인비하비협조", "Q10": "반공직가치관", "Q11": "반공직가치관",
    "Q12": "타인비하비협조", "Q13": "은폐책임전가", "Q14": "답변포기자기붕괴",
    "Q15": "은폐책임전가", "Q16": "위법정당화", "Q19": "답변포기자기붕괴",
    "Q20": "은폐책임전가",
}
# 결격 신호 없는 보통(오탐 없음 검증) / 신호 충분한 우수(우수 도달 검증)
_V2_CLEAR_MID = ["Q1", "Q6", "Q9", "Q13", "Q17", "Q20"]
_V2_CLEAR_HIGH = ["Q1", "Q8", "Q13"]
# 허세(⑤)·서면모순(⑤)·지속침묵(③): 규칙 기반 감지 불가 → LLM 전용(미탐이 정상인 xfail)
_V2_LLM_ONLY = [
    ("Q7", "허세·확신에찬오답(⑤)"), ("Q17", "허세·틀린통계단정(⑤)"),
    ("Q3", "서면-구두 모순(⑤·컨텍스트)"), ("Q18", "지속 침묵·답변포기(③)"),
]

# 경계 케이스 4종 (v2 §F) — 길이 게이트/키워드 카운트 한계 스트레스 테스트.
#  known_limit=True  → MockScorer 오판이 '정상'(LLM 채점기가 교정할 목표점) → 진단 출력.
#  known_limit=False → MockScorer 도 맞혀야 하는 항목 → 하드 PASS.
_V2_BOUNDARY = [
 {"id": "BC-1", "known_limit": True, "real": "우수", "mock_expect": "보통",
  "why": "짧지만 핵심 명중(≈99자<150) → 길이 게이트가 우수를 '보통'으로 과소평가",
  "q": "공무원에게 청렴이 왜 특히 강조된다고 생각하는가?",
  "a": ("청렴은 국민 신뢰의 출발점이기 때문입니다. 공무원의 결정은 세금과 권한을 다루기에, 단 한 번의 "
        "금품 수수도 행정 전체의 공정성을 의심받게 만듭니다. 저는 기준 금액 이하라도 오해의 소지가 "
        "있으면 받지 않는 것을 원칙으로 삼겠습니다.")},
 {"id": "BC-2", "known_limit": True, "real": "보통", "mock_expect": "보통(단 일부 요소 '상' 과대평가)",
  "why": "길지만 공허 → 최종 등급은 보통이나 키워드 나열만으로 헌신열정 등 일부 요소가 '상' 오판",
  "q": "적극행정을 실천하기 위해 어떤 자세가 필요한가?",
  "a": ("저는 적극행정이 정말 중요하다고 생각합니다. 적극행정은 공무원이 적극적으로 행정을 하는 것이고, "
        "국민을 위해서 적극적으로 노력하는 자세가 필요하다고 생각합니다. 그래서 저는 적극적으로 "
        "일하겠습니다. 국민을 위해 봉사하고, 책임감을 가지고, 열정적으로 최선을 다해서, 늘 노력하고 "
        "발전하는 그런 공무원이 되도록 정말 열심히 하겠습니다. 적극적인 자세로 국민께 다가가겠습니다.")},
 {"id": "BC-3", "known_limit": False, "expected": "미흡", "real": "미흡",
  "why": "유창하지만 반공직 → 유창성이 red flag 를 가리지 못함(신규 패턴이 잡아야 함)",
  "q": "공무원을 지원한 동기는 무엇인가?",
  "a": ("안녕하십니까. 저는 어릴 때부터 안정적인 삶을 꿈꿔 왔습니다. 솔직하게 말씀드리면, 공무원의 가장 "
        "큰 매력은 정년이 보장되고 절대 잘리지 않는다는 점이라고 생각합니다. 민간기업처럼 성과에 시달릴 "
        "필요도 없고요. 봉사니 사명감이니 하는 말은 다들 하지만, 저는 그런 것보다는 매달 안정적으로 월급 "
        "받으며 워라밸을 지키는 삶이 훨씬 현실적이고 솔직한 지원 동기라고 생각합니다. 그래서 지원했습니다.")},
 {"id": "BC-4", "known_limit": False, "expected": "보통", "real": "보통",
  "why": "버벅이지만 진솔 → 간투사·휴지는 [등급 미반영](speech_note)로만, 붕괴로 오판 금지",
  "q": "살면서 한계에 부딪혔던 경험과 극복 과정을 말해보라.",
  "a": ("어… 네. 제가… 대학교 2학년 때, 그… 등록금을 벌려고 물류센터에서 야간 아르바이트를 한 적이 "
        "있는데요. 음… 솔직히 처음엔 체력적으로 너무 힘들어서… 그, 며칠 만에 그만두고 싶었습니다. 근데 "
        "어… 같이 일하던 분이, 그… 요령을 알려주시고, 저도 제 나름대로 물건 동선을 좀… 효율적으로 바꿔 "
        "보니까, 어… 두 달을 채워서 목표한 등록금을 다 모았습니다. 그때 어… 힘든 일도 방법을 찾으면 "
        "된다는 걸 배웠습니다.")},
]


def _grade_one(question, answer, committee_ids, written_task=None):
    """v2 회귀용: 세션 1문항을 N위원으로 채점 → (종합등급, 요소판정문자열, red flag 목록)."""
    item = {"qid": "adhoc", "type": "기타", "question": question, "answer": answer}
    if written_task:
        item["written_task"] = written_task
    session = score_session([item], committee_ids=committee_ids)
    ev = session["element_verdicts"]
    return (session["final_grade"],
            "%s%s%s%s" % (ev["소통공감"], ev["헌신열정"], ev["창의혁신"], ev["윤리책임"]),
            session["aggregate"]["red_flag_summary"])


def run_v2_regression(committee_ids=("J-STD", "J-STR", "J-JOB"), verbose=True):
    """
    v2 확장 회귀. 반환: dict(hard_pass, hard_total, xfail_ok, xfail_total,
    known_limit, rows_*). 하드 PASS 대상만 정확도 지표에 계상하고, LLM 전용
    xfail 과 경계 known-limitation 은 진단으로만 출력한다.
    """
    committee_ids = tuple(committee_ids)
    hard_pass = 0
    hard_total = 0
    rows_flag, rows_mid, rows_high, rows_llm, rows_bc = [], [], [], [], []

    # 1) redflag_low (미흡 · 하드 PASS)
    for qid, fam in sorted(_V2_REDFLAG_FAMILY.items(), key=lambda kv: int(kv[0][1:])):
        d = _V2_A[qid]
        got, elem, rf = _grade_one(d["q"], d["미흡"], committee_ids, d.get("written_task"))
        ok = (got == "미흡")
        hard_pass += ok
        hard_total += 1
        rows_flag.append((qid, fam, got, ok, elem, ",".join(rf) or "-"))

    # 2) clear_mid (보통 · 하드 PASS) — 오탐 없음(미흡 보수 판정) 검증
    for qid in _V2_CLEAR_MID:
        d = _V2_A[qid]
        got, elem, rf = _grade_one(d["q"], d["보통"], committee_ids)
        ok = (got == "보통")
        hard_pass += ok
        hard_total += 1
        rows_mid.append((qid, got, ok, elem, ",".join(rf) or "-"))

    # 3) clear_high (우수 · 하드 PASS) — 4요소 신호 충분 시 우수 도달 검증
    for qid in _V2_CLEAR_HIGH:
        d = _V2_A[qid]
        got, elem, rf = _grade_one(d["q"], d["우수"], committee_ids)
        ok = (got == "우수")
        hard_pass += ok
        hard_total += 1
        rows_high.append((qid, got, ok, elem, ",".join(rf) or "-"))

    # 4) llm_only (⑤·③ · xfail) — MockScorer 미탐이 '정상'
    xfail_ok = 0
    for qid, fam in _V2_LLM_ONLY:
        d = _V2_A[qid]
        got, elem, rf = _grade_one(d["q"], d["미흡"], committee_ids, d.get("written_task"))
        undetected = (got != "미흡")     # 규칙이 못 잡는 것이 기대 동작
        xfail_ok += undetected
        rows_llm.append((qid, fam, got, undetected, elem, ",".join(rf) or "-"))

    # 5) 경계 케이스 (BC-1~BC-4)
    for bc in _V2_BOUNDARY:
        got, elem, rf = _grade_one(bc["q"], bc["a"], committee_ids)
        if bc["known_limit"]:
            rows_bc.append((bc["id"], "진단", bc["real"], bc["mock_expect"], got,
                            elem, ",".join(rf) or "-", bc["why"]))
        else:
            ok = (got == bc["expected"])
            hard_pass += ok
            hard_total += 1
            rows_bc.append((bc["id"], "PASS" if ok else "FAIL", bc["real"],
                            bc["expected"], got, elem, ",".join(rf) or "-", bc["why"]))

    out = {"hard_pass": hard_pass, "hard_total": hard_total,
           "xfail_ok": xfail_ok, "xfail_total": len(_V2_LLM_ONLY),
           "rows_flag": rows_flag, "rows_mid": rows_mid, "rows_high": rows_high,
           "rows_llm": rows_llm, "rows_bc": rows_bc}
    if verbose:
        _print_v2_regression(out, committee_ids)
    return out


def _print_v2_regression(out, committee_ids):
    print()
    print("=" * 78)
    print(" 골든셋 v2 회귀 확장 — MockScorer 규칙 커버리지")
    print(" 위원 앙상블: %s (N=%d, 과반=%d)" % (
        ", ".join(committee_ids), len(committee_ids), len(committee_ids)//2+1))
    print("=" * 78)

    print(" [A] red flag 미흡 (신규 트리거 감지 → '미흡' 하드 PASS)")
    print(" %-5s %-14s %-6s %-4s  %s" % ("Q", "트리거계열", "판정", "일치", "요소(소헌창윤)·rf"))
    print(" " + "-" * 74)
    for qid, fam, got, ok, elem, rf in out["rows_flag"]:
        print(" %-5s %-14s %-6s %-4s  %s · %s" % (
            qid, fam, got, "OK" if ok else "FAIL", elem, rf))

    print(" [B] 결격 없음 → 보통 (오탐 없음 · 하드 PASS)")
    print(" %-5s %-6s %-4s  %s" % ("Q", "판정", "일치", "요소(소헌창윤)·rf"))
    print(" " + "-" * 74)
    for qid, got, ok, elem, rf in out["rows_mid"]:
        print(" %-5s %-6s %-4s  %s · %s" % (qid, got, "OK" if ok else "FAIL", elem, rf))

    print(" [C] 4요소 충분 → 우수 (하드 PASS)")
    print(" %-5s %-6s %-4s  %s" % ("Q", "판정", "일치", "요소(소헌창윤)·rf"))
    print(" " + "-" * 74)
    for qid, got, ok, elem, rf in out["rows_high"]:
        print(" %-5s %-6s %-4s  %s · %s" % (qid, got, "OK" if ok else "FAIL", elem, rf))

    print(" [D] LLM 전용 xfail — 허세(⑤)·서면모순(⑤)·지속침묵(③): 규칙 미탐이 정상")
    print(" %-5s %-22s %-6s %-8s  %s" % ("Q", "미탐대상", "규칙판정", "미탐(정상)", "요소(소헌창윤)"))
    print(" " + "-" * 74)
    for qid, fam, got, undetected, elem, rf in out["rows_llm"]:
        mark = "OK(미탐)" if undetected else "감지됨!"
        print(" %-5s %-22s %-6s %-8s  %s · %s" % (qid, fam, got, mark, elem, rf))

    print(" [E] 경계 케이스 (BC-1~BC-4) — 길이/키워드 게이트 한계 시험")
    print(" %-5s %-6s %-6s %-6s %-6s  %s" % ("BC", "구분", "실제", "기대/예상", "판정", "요소·비고"))
    print(" " + "-" * 74)
    for row in out["rows_bc"]:
        bid, kind, real, exp, got, elem, rf, why = row
        print(" %-5s %-6s %-6s %-6s %-6s  %s · %s" % (bid, kind, real, exp, got, elem, rf))
        print("       └ %s" % why)

    hp, ht = out["hard_pass"], out["hard_total"]
    print("-" * 78)
    print(" 하드 PASS 정확도: %d/%d (%.0f%%)  |  LLM 전용 xfail 미탐확인: %d/%d  |  known-limit 진단: %d건" % (
        hp, ht, 100.0*hp/ht if ht else 0.0,
        out["xfail_ok"], out["xfail_total"],
        sum(1 for r in out["rows_bc"] if r[1] == "진단")))
    print("=" * 78)


def run_full_regression(committee_ids=("J-STD", "J-STR", "J-JOB"), verbose=True):
    """v1 축소판(9) + v2 확장 회귀를 함께 실행. 반환: (v1_pass, v1_total, v2_out)."""
    v1_pass, v1_total, _ = run_golden_regression(committee_ids=committee_ids, verbose=verbose)
    v2_out = run_v2_regression(committee_ids=committee_ids, verbose=verbose)
    if verbose:
        tot_p = v1_pass + v2_out["hard_pass"]
        tot_t = v1_total + v2_out["hard_total"]
        print()
        print("★ 종합: 하드 PASS %d/%d (v1 %d/%d + v2 %d/%d) · "
              "LLM 전용 xfail %d/%d 미탐확인 · known-limit %d건(BC-1/BC-2)" % (
                  tot_p, tot_t, v1_pass, v1_total,
                  v2_out["hard_pass"], v2_out["hard_total"],
                  v2_out["xfail_ok"], v2_out["xfail_total"],
                  sum(1 for r in v2_out["rows_bc"] if r[1] == "진단")))
    return v1_pass, v1_total, v2_out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main():
    ap = argparse.ArgumentParser(description="공무원 AI 면접 채점기 프로토타입(Mock)")
    ap.add_argument("--selftest", action="store_true",
                    help="골든셋 회귀(v1 축소판 9 + v2 확장) 실행")
    ap.add_argument("--v1only", action="store_true",
                    help="v1 축소판 회귀만 실행(v2 확장 생략)")
    ap.add_argument("--committees", default="J-STD,J-STR,J-JOB",
                    help="위원 페르소나 CSV (기본 3인 트랙)")
    ap.add_argument("--question", default=None)
    ap.add_argument("--answer", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    committees = tuple(c.strip() for c in args.committees.split(",") if c.strip())

    if args.selftest or (not args.question):
        if args.v1only:
            run_golden_regression(committee_ids=committees)
        else:
            run_full_regression(committee_ids=committees)
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
