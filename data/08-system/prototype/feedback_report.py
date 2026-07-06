# -*- coding: utf-8 -*-
"""
feedback_report.py — 응시자용 피드백 리포트 생성기 프로토타입 (표준 라이브러리만)

설계 원천:
- data/08-system/채점-프롬프트-실장.md §4 (피드백 생성 프롬프트/스키마)
- data/06-answer-guides/평가루브릭-설계.md §3-2 (스피치 지표), §4-3-⑤ (파이프라인)

역할: 확정된 채점 결과(scorer.score_session 출력)를 **재채점 없이** 응시자용
마크다운 리포트로 렌더한다. 등급/요소판정을 바꾸지 않고, 근거 인용과 코칭 텍스트만
조립한다. 비언어·스피치는 등급과 분리해 코칭 채널로만 노출한다(§4-1 규칙 3·5).

핵심 함수: generate_report(session_result) -> markdown 문자열.

주의: 스피치 코칭은 규칙 기반 스텁이며 실제 음성 분석(CPM·필러·침묵)을 대체하지 않는다.
문장 조립도 규칙 기반 근사치로, 실제 서비스는 §4 피드백 LLM(Sonnet급)이 담당한다.
"""

import re

try:
    from . import scorer as _scorer
except Exception:  # 단독 실행/스크립트 임포트
    import scorer as _scorer

ELEMENTS = _scorer.ELEMENTS
ELEMENT_LABEL = {
    "소통공감": "소통·공감", "헌신열정": "헌신·열정",
    "창의혁신": "창의·혁신", "윤리책임": "윤리·책임",
}

GRADE_HEADLINE = {
    "우수": "네 요소를 고르게 충족한 우수한 답변이었습니다.",
    "보통": "결격 신호 없이 무난하게 마친 결과입니다. 대다수 응시자가 받는 정상 범위의 등급입니다.",
    "미흡": "전달은 무난했지만 일부 요소에서 결격 신호가 나와 아쉬운 결과입니다.",
}

GRADE_EXPLAIN = {
    "우수": "위원 과반이 네 평정요소 모두를 '상'으로 보아 우수로 집계되었습니다.",
    "보통": "'하'로 판정된 요소가 과반에 이르지 않아, 우수·미흡 어느 조건에도 해당하지 "
            "않는 보통으로 집계되었습니다. 실력 부족이 아니라 가장 흔한 정상 결과입니다.",
    "미흡": "답변 실력이 부족해서가 아니라, 아래 인용된 표현이 공직 가치·윤리의 결격 "
            "신호로 평가되어 위원 과반이 해당 요소를 '하'로 보았기 때문입니다.",
}

# 다음 연습 질문 뱅크 — 보강할 요소별 추천(약점 보정용).
PRACTICE_BANK = {
    "소통공감": [("상황형",
                "민원인이 다른 창구에서 이미 안내받았다며 같은 요구를 반복합니다. 어떻게 응대하시겠습니까?",
                "경청→공감→핵심 확인의 순서 보강")],
    "헌신열정": [("인성",
                "공직에 들어와 가장 이루고 싶은 목표 한 가지와 그 준비 과정을 말씀해 주세요.",
                "공직 동기의 구체성(경험 근거·준비 행동) 보강")],
    "창의혁신": [("직무",
                "적극행정과 소극행정의 차이를 사례로 설명해 보세요.",
                "원인→우선순위→단계적 실행의 전략적 사고 보강")],
    "윤리책임": [("상황형",
                "본인의 실수로 민원 처리가 잘못된 것을 아무도 모르게 발견했다면 어떻게 하시겠습니까?",
                "책임 귀속·은폐 회피 연습")],
}


# ---------------------------------------------------------------------------
# 근거 수집 (재채점 없이 위원 결과에서 인용/근거만 취합)
# ---------------------------------------------------------------------------

def _collect_evidence(session_result):
    """
    요소별로 위원 근거(reasoning/evidence)와 red flag 를 취합.
    반환: {element: {"verdicts":[..], "reasoning":[..], "quotes":[..], "red_flags":[..]}}
    """
    acc = {e: {"verdicts": [], "reasoning": [], "quotes": [], "red_flags": []}
           for e in ELEMENTS}
    for cid, per_answer in session_result["results"].items():
        for qid, sc in per_answer.items():
            for e in ELEMENTS:
                el = sc["elements"][e]
                acc[e]["verdicts"].append(el["verdict"])
                if el["reasoning"] not in acc[e]["reasoning"]:
                    acc[e]["reasoning"].append(el["reasoning"])
                for q in el["evidence"]:
                    if q and q not in acc[e]["quotes"]:
                        acc[e]["quotes"].append(q)
            for rf in sc.get("red_flags", []):
                key = (rf["type"], rf["quote"])
                if key not in [(x["type"], x["quote"]) for x in acc[rf["element"]]["red_flags"]]:
                    acc[rf["element"]]["red_flags"].append(rf)
    return acc


def _speech_metrics(session_result):
    """규칙 기반 스피치 지표 스텁(등급 미반영). 전사문 텍스트에서 근사 산출."""
    items = []
    for it in session_result["items"]:
        answer = it["answer"]
        spoken = _scorer._spoken_text(answer)
        dense = _scorer._dense_len(spoken)
        # 발화 시간 추정: 한국어 면접 표준 ~350 CPM 가정 → 초 환산(데모).
        est_sec = round(dense / (350.0 / 60.0), 1) if dense else 0.0
        fillers = len(re.findall(r"(음+|어+[.,\s]|그+[.,\s]|약간|뭐랄까|좀)", spoken))
        long_pause = len(re.findall(r"침묵|한숨|…|\.\.\.", answer))
        items.append({
            "qid": it["qid"], "chars": dense, "est_sec": est_sec,
            "filler": fillers, "long_pause": long_pause,
        })
    return items


def _speech_coaching(metrics):
    """스피치 지표 → 코칭 문구(스텁, 등급 미반영)."""
    tips = []
    total_chars = sum(m["chars"] for m in metrics)
    total_sec = sum(m["est_sec"] for m in metrics)
    avg_sec = total_sec / len(metrics) if metrics else 0
    total_filler = sum(m["filler"] for m in metrics)
    total_pause = sum(m["long_pause"] for m in metrics)

    if avg_sec and avg_sec < 20:
        tips.append("답변당 발화 추정 %.0f초로 다소 짧습니다. 핵심 사례 1개를 더해 "
                    "30초~1분으로 늘려 보세요." % avg_sec)
    elif avg_sec >= 20:
        tips.append("답변 분량(추정 평균 %.0f초)은 안정적입니다. 이 페이스를 유지하세요." % avg_sec)
    if total_filler >= 3:
        tips.append("간투사(음/어/그 등)가 %d회 감지됩니다. 문장 사이 짧은 정적으로 "
                    "대체해 보세요." % total_filler)
    if total_pause:
        tips.append("긴 침묵/한숨이 %d회 관찰됩니다. 2~3초 생각 정리는 정상이니, 침묵이 "
                    "길어지면 '한 가지 예를 들면'으로 이어가 보세요." % total_pause)
    if not tips:
        tips.append("특이 사항이 감지되지 않았습니다.")
    return tips


# ---------------------------------------------------------------------------
# 리포트 조립
# ---------------------------------------------------------------------------

def generate_report(session_result):
    """
    session_result: scorer.score_session(...) 출력.
    반환: 응시자용 피드백 리포트(마크다운 문자열).
    """
    grade = session_result["final_grade"]
    ev_map = session_result["element_verdicts"]
    agg = session_result["aggregate"]
    evidence = _collect_evidence(session_result)
    metrics = _speech_metrics(session_result)

    lines = []
    add = lines.append

    # 헤더
    add("# 모의면접 피드백 리포트")
    add("")
    q_types = ", ".join(sorted(set(it["type"] for it in session_result["items"])))
    add("- 문항 수: %d개 (유형: %s)" % (len(session_result["items"]), q_types))
    add("- 위원 앙상블: %s (N=%d, 과반=%d)" % (
        ", ".join(session_result["committee_ids"]), agg["N"], agg["majority"]))
    add("")

    # 종합 등급
    add("## 1. 종합 등급: **%s**" % grade)
    add("")
    add("> %s" % GRADE_HEADLINE.get(grade, ""))
    add("")
    add(GRADE_EXPLAIN.get(grade, ""))
    add("")
    add("- 판정 근거(집계 규칙): %s" % agg["decisive_rule"])
    if agg["red_flag_summary"]:
        add("- 감지된 결격 신호: %s" % ", ".join(agg["red_flag_summary"]))
    add("")
    add("| 평정요소 | 세션 대표 판정 |")
    add("|---|---|")
    for e in ELEMENTS:
        add("| %s | %s |" % (ELEMENT_LABEL[e], ev_map[e]))
    add("")

    # 강점
    add("## 2. 잘한 점 (강점)")
    add("")
    strengths = [e for e in ELEMENTS if ev_map[e] == "상"]
    if strengths:
        for e in strengths:
            q = evidence[e]["quotes"][0] if evidence[e]["quotes"] else ""
            add("- **%s** — 핵심 요건을 충족했습니다." % ELEMENT_LABEL[e])
            if q:
                add("  - 근거 인용: “%s”" % q)
    else:
        add("- 두드러진 '상' 요소는 없지만, 결격 없이 무난히 전달했습니다. "
            "아래 개선점을 반영하면 강점 요소를 만들 수 있습니다.")
    add("")

    # 개선점
    add("## 3. 개선점")
    add("")
    improved_any = False
    for e in ELEMENTS:
        v = ev_map[e]
        if v == "하":
            improved_any = True
            rfs = evidence[e]["red_flags"]
            add("- **%s (하)**" % ELEMENT_LABEL[e])
            if rfs:
                for rf in rfs[:2]:
                    add("  - 무엇이: %s" % rf["note"])
                    add("  - 근거 인용: “%s”" % rf["quote"])
                    add("  - 교정 방향: %s" % _fix_hint(e, rf["type"]))
            else:
                add("  - 교정 방향: %s" % _fix_hint(e, None))
        elif v == "중":
            improved_any = True
            add("- **%s (중)** — 방향은 맞으나 근거·구체성을 보강하면 '상'에 가까워집니다. "
                "결론(두괄식)→경험/수치 근거→공직 적용 순서를 갖춰 보세요." % ELEMENT_LABEL[e])
    if not improved_any:
        add("- 네 요소 모두 '상'입니다. 현재 수준을 유지하며 답변 길이·페이스만 관리하세요.")
    add("")

    # 모범답변 방향
    add("## 4. 모범답변 방향 (대본이 아닌 뼈대)")
    add("")
    add("- 결론(두괄식) → 근거(경험·수치·사례) → 공직 적용의 3단 구조를 기본으로 합니다.")
    add("- 상황형은 **확인 → 근거 기반 재건의/대안 → 절차(보고·행동강령) 대응 → 관계 회복**의 "
        "4단계로 극단(즉시 거부/즉시 순응)을 피합니다.")
    add("- 판단 기준으로 **법령·공익**을 명시하고, 상대(민원인·동료·상사) 관점을 1회 이상 언급합니다.")
    add("")

    # 스피치 코칭 (등급 미반영)
    add("## 5. 스피치 코칭 (등급 미반영 · 참고용)")
    add("")
    add("> 아래는 채점 등급에 **반영되지 않는** 말하기 코칭입니다. (규칙 기반 스텁 — 실제 "
        "서비스는 음성 분석으로 CPM·필러·침묵을 측정합니다.)")
    add("")
    for tip in _speech_coaching(metrics):
        add("- %s" % tip)
    add("")

    # 다음 연습 질문
    add("## 6. 다음 연습 질문")
    add("")
    recs = _next_practice(ev_map)
    if recs:
        for qtype, question, why in recs:
            add("- [%s] %s" % (qtype, question))
            add("  - 보강 목적: %s" % why)
    else:
        add("- 특정 약점 요소가 없어, 다양한 유형을 고르게 연습해 보시길 권합니다.")
    add("")

    # 격려
    add("## 7. 마무리")
    add("")
    add("> %s" % _encouragement(grade))
    add("")

    return "\n".join(lines)


def _fix_hint(element, rf_type):
    hints = {
        ("윤리책임", "위법정당화"):
            "'먼저 지시의 배경·근거를 확인하고, 위법 소지가 있으면 관련 법령을 정리해 정중히 "
            "재검토를 건의하겠다'로 바꿔 보세요.",
        ("윤리책임", "은폐책임전가"):
            "책임 회피 대신 '조직을 위법 위험에서 보호하는 것도 제 역할'이라는 능동적 태도를 "
            "보여 주세요. 실수는 즉시 보고가 원칙입니다.",
        ("윤리책임", "진술모순"):
            "서면 과제와 구두 답변의 일관성을 맞추세요. 강점을 뒤집는 진술은 신뢰를 크게 떨어뜨립니다.",
        ("소통공감", "타인비하비협조"):
            "상대를 탓하기 전에 '먼저 사정을 들어보겠다'는 경청·공감 표현으로 시작해 보세요.",
        ("헌신열정", "반공직가치관"):
            "안정성은 부차적 이유로 두고, 계기→준비 행동→공직 적용으로 이어지는 구체적 동기를 "
            "제시하세요.",
        ("소통공감", "답변포기자기붕괴"):
            "2~3초 정리 후 '한 가지 예를 들면'으로 답을 이어가면 붕괴를 피할 수 있습니다.",
    }
    if (element, rf_type) in hints:
        return hints[(element, rf_type)]
    return "결론을 먼저 말하고, 법령·공익을 판단 기준으로 명시한 뒤 절차(확인·보고·협의)를 덧붙이세요."


def _next_practice(element_verdicts):
    recs = []
    # '하' 요소 우선, 그다음 '중'
    for target in ("하", "중"):
        for e in ELEMENTS:
            if element_verdicts[e] == target and e in PRACTICE_BANK:
                for rec in PRACTICE_BANK[e]:
                    if rec not in recs:
                        recs.append(rec)
    return recs[:3]


def _encouragement(grade):
    if grade == "미흡":
        return ("결격 신호는 표현만 바꾸면 충분히 교정됩니다. 위 방향으로 한 번 더 연습해 "
                "보시면 크게 달라질 거예요.")
    if grade == "우수":
        return "핵심 구조를 잘 갖추셨습니다. 다양한 유형에서도 같은 완성도를 유지해 보세요."
    return ("결격 없이 무난히 마치셨습니다. 근거와 구체성을 조금만 더하면 강점 요소가 "
            "늘어날 거예요.")


# ---------------------------------------------------------------------------
# 데모
# ---------------------------------------------------------------------------

def _demo():
    # 골든셋 Q9 미흡 답변으로 리포트 데모(2인 트랙).
    triad = next(t for t in _scorer.GOLDEN_TRIADS if t["qid"] == "Q9")
    item = {"qid": "Q9", "type": "상황형",
            "question": triad["question"], "answer": triad["answers"]["미흡"]}
    session = _scorer.score_session([item], committee_ids=("J-STD", "J-STR"))
    print(generate_report(session))


if __name__ == "__main__":
    _demo()
