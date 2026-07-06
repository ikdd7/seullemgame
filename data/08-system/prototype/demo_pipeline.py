#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demo_pipeline.py — 공무원 AI 모의면접 MVP 4개 프로토타입 통합 데모 (표준 라이브러리만)

이 스크립트는 프로토타입 4개 모듈을 한 번의 실행으로 잇는다.

  [1] 질문 선택      question_selector.select_questions(...)   → 유형 쿼터 기반 질문 큐
        │  (region/job/track/difficulty/seed → 면접 순서로 정렬된 seq)
        ▼
  [2] 면접 진행      session_engine.SessionEngine(...).run()   → MockLLMClient 면접관 발화 +
        │            DemoAnswerProvider 자동 답변 + 꼬리질문 트리거 → 세션 로그(log)
        ▼
  [3] 각 답변 채점   scorer.score_session(items, committee_ids) → 위원 N인 × 문항별 §1-4 채점
        │            (여기서 '위원 앙상블 집계' = aggregate_verdicts 과반 규칙까지 포함)
        ▼
  [4] 위원 앙상블 집계  session_result["aggregate"]              → 우수/보통/미흡 종합 등급
        ▼
  [5] 피드백 리포트  feedback_report.generate_report(...)       → 응시자용 마크다운 리포트

전부 Mock 백엔드(MockLLMClient / MockScorer)라 API 키 없이 결정적으로 완주한다.
원본 4개 모듈은 수정하지 않는다. 모듈 시그니처가 서로 맞지 않는 지점은 이 파일 안의
'어댑터 함수'(_build_scoring_items / _committee_ids_for)로만 이어 붙인다.

어댑터가 메우는 시그니처 간극(원본 무수정):
  - session_engine 은 '세션 로그(list of dict)'를 내보내고, scorer 는
    '[{qid,type,question,answer}, ...]' 리스트를 입력으로 받는다. 이 형태 변환을
    _build_scoring_items 가 담당한다.
      · question(원문 텍스트)/type 은 질문 선택 결과(plan["seq"])의 question 에서 가져온다.
        (로그의 면접관 발화는 페르소나 어조가 덧입혀진 문장이라 원문이 아니다.)
      · answer 는 로그에서 같은 qid 의 지원자 발화(주답변 + 꼬리질문 답변)를 순서대로
        이어 붙여 '답변 스레드' 하나로 만든다. (scorer 는 문항당 답변 1개를 채점하므로.)
  - 면접에 투입된 위원 수(2인/3인 트랙)에 맞춰 채점 위원 앙상블 규모를
    _committee_ids_for 가 결정한다(2인→J-STD/J-STR, 3인→+J-JOB).
"""

import argparse
import os
import sys

# 같은 prototype/ 디렉터리의 모듈들을 import 할 수 있도록 경로 보정
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import question_selector as qs      # noqa: E402  [1] 질문 선택
import session_engine as se         # noqa: E402  [2] 면접 진행
import scorer as sc                 # noqa: E402  [3][4] 채점 + 앙상블 집계
import feedback_report as fr        # noqa: E402  [5] 피드백 리포트


# ===========================================================================
# 출력 유틸
# ===========================================================================
def _banner(step, title):
    print()
    print("#" * 78)
    print("#  단계 %s · %s" % (step, title))
    print("#" * 78)


# ===========================================================================
# 어댑터 1 — 세션 로그 → scorer 입력 items
# ===========================================================================
def _build_scoring_items(plan, log):
    """
    질문 선택 결과(plan)와 세션 로그(log)를 scorer.score_session 입력 형태로 변환.

    plan["seq"] : [{"phase","tier","question":{id,type,text,...}}, ...]  ← 원문/유형/순서
    log         : [{"t","state","role","persona","qid","trigger","text"}, ...]  ← 발화 스트림

    반환: [{"qid","type","question","answer"}, ...]  (질문 순서 유지)
          answer = 같은 qid 의 지원자 발화(주답변 + 꼬리질문 답변)를 순서대로 연결.
    """
    # 질문 순서 + 원문/유형 인덱스
    order = []
    qinfo = {}
    for item in plan["seq"]:
        q = item["question"]
        qid = q.get("id")
        if qid in qinfo:
            continue
        qinfo[qid] = q
        order.append(qid)

    # qid 별 지원자 발화 수집(로그 순서 = 발화 순서)
    answers = {qid: [] for qid in qinfo}
    for entry in log:
        if entry.get("role") == "지원자" and entry.get("qid") in answers:
            txt = (entry.get("text") or "").strip()
            if txt:
                answers[entry["qid"]].append(txt)

    items = []
    for qid in order:
        q = qinfo[qid]
        items.append({
            "qid": qid,
            "type": q.get("type"),
            "question": (q.get("text") or "").replace("\n", " ").strip(),
            "answer": " ".join(answers[qid]).strip(),
        })
    return items


# ===========================================================================
# 어댑터 2 — 면접 위원 수 → 채점 위원 앙상블 구성
# ===========================================================================
def _committee_ids_for(personas):
    """면접에 투입된 페르소나 수에 맞춰 채점 위원 앙상블을 정한다.
    2인 트랙(서울·부산 등) → (J-STD, J-STR), 3인 트랙 → (J-STD, J-STR, J-JOB)."""
    if len(personas) >= 3:
        return ("J-STD", "J-STR", "J-JOB")
    return ("J-STD", "J-STR")


# ===========================================================================
# 파이프라인
# ===========================================================================
def run_pipeline(region, job, track="지방직표준", difficulty="실전", seed=42,
                 questions=None):
    """4개 모듈을 순서대로 잇는 통합 실행. 반환: (session_result, report_md)."""

    # -- 공통 입력: 질문 뱅크는 한 번만 로드해 두 모듈에 공유 --------------
    if questions is None:
        questions = qs.load_questions()

    # -----------------------------------------------------------------
    # [1] 질문 선택 — question_selector
    # -----------------------------------------------------------------
    _banner(1, "질문 선택 (question_selector.select_questions)")
    plan = qs.select_questions(
        region=region, job=job, track=track, difficulty=difficulty,
        questions=questions, seed=seed,
    )
    q = plan["quota"]
    print("쿼터: " + "  ".join("%s%d" % (k, v) for k, v in q.items() if v)
          + "  (합계 %d)" % sum(q.values()))
    print("선택된 주질문 %d개 (유형 순):" % len(plan["seq"]))
    for i, item in enumerate(plan["seq"], 1):
        qq = item["question"]
        text = (qq.get("text") or "").replace("\n", " ")
        if len(text) > 46:
            text = text[:45] + "…"
        print("  %2d. [%-5s] %-46s (id=%s type=%s)"
              % (i, item["phase"], text, qq.get("id"), qq.get("type")))
    print("진단(유형별 충족/완화단계):")
    for t, d in plan["diagnostics"].items():
        if d["need"] == 0:
            continue
        flag = "  ⚠ 부족 %d건" % d["shortfall"] if d["shortfall"] > 0 else ""
        print("  - %s: %d/%d%s" % (t, d["got"], d["need"], flag))

    # -----------------------------------------------------------------
    # [2] 면접 진행 — session_engine (MockLLM 면접관 + Demo 자동 답변)
    # -----------------------------------------------------------------
    _banner(2, "면접 진행 (session_engine.SessionEngine.run · MockLLMClient)")
    engine = se.SessionEngine(
        region=region, job=job, track=track, difficulty=difficulty,
        llm=se.MockLLMClient(), provider=se.DemoAnswerProvider(),
        seed=seed, questions=questions,
    )
    # 결정성 확인: 엔진이 내부에서 다시 뽑은 질문 큐가 [1] 과 동일해야 한다.
    assert [it["question"]["id"] for it in engine.plan["seq"]] \
        == [it["question"]["id"] for it in plan["seq"]], \
        "질문 선택 결과가 결정적이지 않음(엔진 재계산 불일치)"
    log = engine.run()   # 면접 진행 로그를 stdout 으로 출력하고 세션 로그를 반환

    # -----------------------------------------------------------------
    # [3] 각 답변 채점 + [4] 위원 앙상블 집계 — scorer
    #     (session_engine 의 SCORING 은 스텁이므로, 여기서 실제 채점으로 대체)
    # -----------------------------------------------------------------
    _banner("3·4", "각 답변 채점 + 위원 앙상블 집계 (scorer.score_session · MockScorer)")
    items = _build_scoring_items(plan, log)                 # ← 어댑터 1
    committee_ids = _committee_ids_for(engine.personas)     # ← 어댑터 2
    print("채점 위원 앙상블: %s (N=%d, 과반=%d)"
          % (", ".join(committee_ids), len(committee_ids), len(committee_ids) // 2 + 1))
    print("문항별 답변 스레드 → 위원별 개인등급:")
    session_result = sc.score_session(items, committee_ids=committee_ids)
    for it in items:
        qid = it["qid"]
        grades = [session_result["results"][cid][qid]["member_grade"]
                  for cid in committee_ids]
        alen = len(it["answer"])
        print("  - %-8s [%-5s] 답변 %3d자 → %s"
              % (qid, it["type"], alen, "/".join(grades)))
    agg = session_result["aggregate"]
    ev = session_result["element_verdicts"]
    print("-" * 78)
    print("세션 대표 요소판정(소통/헌신/창의/윤리): %s / %s / %s / %s"
          % (ev["소통공감"], ev["헌신열정"], ev["창의혁신"], ev["윤리책임"]))
    print("감지된 red flag 계열: %s" % (", ".join(agg["red_flag_summary"]) or "없음"))
    print("종합 등급: %s" % session_result["final_grade"])
    print("집계 규칙: %s" % agg["decisive_rule"])

    # -----------------------------------------------------------------
    # [5] 피드백 리포트 — feedback_report (재채점 없이 렌더)
    # -----------------------------------------------------------------
    _banner(5, "피드백 리포트 생성 (feedback_report.generate_report)")
    report_md = fr.generate_report(session_result)
    print(report_md)

    return session_result, report_md


# ===========================================================================
# CLI
# ===========================================================================
def main():
    ap = argparse.ArgumentParser(
        description="공무원 AI 모의면접 4개 프로토타입 통합 데모 파이프라인")
    ap.add_argument("--region", required=True, help="지자체명 (예: 서울특별시)")
    ap.add_argument("--job", required=True, help="직렬명 (예: 일반행정직)")
    ap.add_argument("--track", default="지방직표준",
                    choices=list(qs.QUOTA_TRACKS.keys()), help="면접 트랙")
    ap.add_argument("--difficulty", default="실전", choices=["실전", "초급"],
                    help="난이도 모드")
    ap.add_argument("--seed", type=int, default=42, help="랜덤 시드(결정적 재현)")
    ap.add_argument("--save", nargs="?", const="__AUTO__", default=None,
                    metavar="PATH",
                    help="피드백 리포트를 마크다운 파일로 저장(경로 생략 시 자동 파일명)")
    args = ap.parse_args()

    session_result, report_md = run_pipeline(
        region=args.region, job=args.job, track=args.track,
        difficulty=args.difficulty, seed=args.seed,
    )

    if args.save is not None:
        path = args.save
        if path == "__AUTO__":
            safe = lambda s: "".join(c if c.isalnum() else "_" for c in s)
            path = os.path.join(
                os.getcwd(),
                "feedback_%s_%s_seed%d.md" % (safe(args.region), safe(args.job), args.seed))
        with open(path, "w", encoding="utf-8") as f:
            f.write(report_md)
        print()
        print("[저장] 피드백 리포트를 파일로 저장했습니다: %s" % path)


if __name__ == "__main__":
    main()
