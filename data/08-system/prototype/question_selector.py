#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
공무원 AI 모의면접 — 질문 선택 엔진 프로토타입 (MVP)

설계 근거:
  - data/06-answer-guides/모의면접-세션-설계.md  §3 (질문 선택 알고리즘)
  - data/08-system/아키텍처-종합설계.md            §4-1 (질문 출제 플로우)
  - data/07-structured/questions.json             (질문 뱅크, 3,240건)

핵심 아이디어(설계 §3-2, 리포트 §5-3의 "축 분리 조합"):
  지역×직렬 교차 태깅이 희소(3.4%)하므로, 단일 교차 매칭에 의존하지 않고
  "지역 축(지역현안) + 직렬 축(직무)"을 각각 뽑아 유형별 쿼터로 조합한다.

표준 라이브러리만 사용. 결정적(seed 고정) 동작.
"""

import argparse
import json
import math
import os
import random
import unicodedata
from collections import defaultdict

# ---------------------------------------------------------------------------
# 기본 경로: 이 파일 기준으로 questions.json 위치를 계산 (repo 루트/data/07-structured)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
DEFAULT_QUESTIONS_PATH = os.path.join(
    _REPO_ROOT, "data", "07-structured", "questions.json"
)

# ---------------------------------------------------------------------------
# 유형별 쿼터 (설계 §3-2). 트랙/지역별로 조정.
# ---------------------------------------------------------------------------
# 순서 있는 튜플로 두어 재현성 확보.
QUOTA_TRACKS = {
    # 지방직 표준형 (기본값): 공직가치2 + 인성2 + 직무3 + 지역현안2 + 상황형1 = 10
    "지방직표준": {"공직가치": 2, "인성": 2, "직무": 3, "지역현안": 2, "상황형": 1},
    # 국가직 9급형(⑤단계): 지역현안 0, 상황형 3, region!=null 전량 제외
    "국가직9급": {"공직가치": 2, "인성": 2, "직무": 3, "지역현안": 0, "상황형": 3},
}

# 지역 프로파일별 쿼터 오버라이드 (설계 §3-2 표)
QUOTA_REGION_OVERRIDE = {
    # 서울: 인성 강화, 퀴즈식 지역질문 지양(지역현안 1)
    "서울특별시": {"공직가치": 2, "인성": 3, "직무": 3, "지역현안": 1, "상황형": 1},
    # 대구: 지역현안 +1 (지역질문 강세)
    "대구광역시": {"공직가치": 2, "인성": 1, "직무": 3, "지역현안": 3, "상황형": 1},
    # 인천: 토론 모드가 별도 1블록 차지 -> 직무/지역현안 -1
    "인천광역시": {"공직가치": 2, "인성": 2, "직무": 2, "지역현안": 2, "상황형": 1},
}

# 유형 선택 가중치 테이블 (설계 §3-2)
W_RELIABILITY = {
    "확인": 1.0,
    "기출": 0.9,
    "복원": 0.8,
    "빈출": 0.7,
    "예상": 0.5,
    None: 0.4,
}
# 초급 모드에서 '고신뢰'로 취급하는 라벨 (아키텍처 §3-2)
HIGH_RELIABILITY = {"확인", "복원", "기출", "빈출"}

# 출제 순서 골격 (설계 §3-3). phase 라벨과 우선 배치 순서.
# 오프닝(인성) -> 공직가치 -> 직무 -> 지역현안 -> 상황형 -> 마무리
PHASE_ORDER = ["오프닝", "공직가치", "직무", "지역현안", "상황형", "마무리"]


# ---------------------------------------------------------------------------
# 로더
# ---------------------------------------------------------------------------
def load_questions(path=None):
    """questions.json 로드 후 questions 리스트 반환."""
    if path is None:
        path = DEFAULT_QUESTIONS_PATH
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["questions"]


# ---------------------------------------------------------------------------
# 가중치 계산
# ---------------------------------------------------------------------------
def w_reliability(q):
    return W_RELIABILITY.get(q.get("reliability"), 0.4)


def w_year(q):
    """연도 최신성 가중 (설계 §3-2)."""
    y = q.get("year")
    if y is None:
        return 0.9
    if y >= 2024:
        return 1.2
    if y >= 2020:
        return 1.0
    return 0.7


def w_novelty(q, recent_ids):
    """재출제 억제: 최근 3세션 출제분은 0.1 (설계 §3-2)."""
    return 0.1 if q.get("id") in recent_ids else 1.0


def weight(q, recent_ids):
    return w_reliability(q) * w_year(q) * w_novelty(q, recent_ids)


# ---------------------------------------------------------------------------
# 후보 필터링 (완화 단계) — 설계 §3-1 / 아키텍처 §4-1
# ---------------------------------------------------------------------------
def _tier1(pool, region, job):
    """1순위: region == 선택 AND job == 선택."""
    return [q for q in pool if q.get("region") == region and q.get("job") == job]


def _tier2(pool, region, job):
    """2순위: (region==선택 AND job==null) + (job==선택 AND region==null) — 축 분리 조합."""
    return [
        q
        for q in pool
        if (q.get("region") == region and q.get("job") is None)
        or (q.get("job") == job and q.get("region") is None)
    ]


def _tier3(pool):
    """3순위: category == common (지역·직렬 무관 공통)."""
    return [q for q in pool if q.get("category") == "common"]


def build_tiered_candidates(pool, region, job, exclude_regional=False):
    """
    완화 단계별 후보 리스트를 반환.
    각 단계는 '누적'이 아니라 단계별 신규 후보 집합. 소비 로직에서 순차 확장한다.
    exclude_regional=True (국가직) 이면 region!=null 항목 전량 제외.
    """
    if exclude_regional:
        pool = [q for q in pool if q.get("region") is None]
    return [
        _tier1(pool, region, job),
        _tier2(pool, region, job),
        _tier3(pool),
    ]


# ---------------------------------------------------------------------------
# 중복 제거 (설계 §3-1 [2])
#   프로토타입은 임베딩이 없으므로 정규화 텍스트 기준 근사 중복 제거.
#   동일(정규화) 텍스트는 reliability 우선순위가 높은 쪽만 유지.
# ---------------------------------------------------------------------------
def _norm_text(t):
    t = unicodedata.normalize("NFKC", t or "")
    t = "".join(ch for ch in t if not ch.isspace())
    return t.lower()


def dedupe(questions):
    best = {}
    order = []
    for q in questions:
        key = _norm_text(q.get("text"))
        if key not in best:
            best[key] = q
            order.append(key)
        else:
            # reliability 높은 쪽 유지
            if w_reliability(q) > w_reliability(best[key]):
                best[key] = q
    return [best[k] for k in order]


# ---------------------------------------------------------------------------
# 가중 비복원 샘플링 (Efraimidis-Spirakis). seed 고정으로 결정적.
# ---------------------------------------------------------------------------
def weighted_sample_without_replacement(items, weights, k, rng):
    if k <= 0 or not items:
        return []
    keyed = []
    for it, w in zip(items, weights):
        w = max(w, 1e-9)
        u = rng.random()
        # key = u^(1/w); 큰 key 우선. 로그 공간으로 안정 계산.
        key = math.log(u) / w
        keyed.append((key, it))
    # key 내림차순 (log(u)/w 는 음수이므로 0에 가까운(=큰) 것 우선)
    keyed.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in keyed[:k]]


# ---------------------------------------------------------------------------
# 유형별 쿼터 채우기 (완화 단계 + 가중 샘플링)
# ---------------------------------------------------------------------------
def fill_type_quota(qtype, need, tiers, recent_ids, chosen_ids, rng, beginner=False):
    """
    특정 유형에 대해 need개를 채운다.
    tiers: [tier1, tier2, tier3] (완화 단계). 좁은 단계부터 부족분을 단계적으로 확장.
    반환: (선택된 질문 리스트, 실제 채운 수, 마지막으로 사용한 완화 단계 인덱스+1)
    """
    picked = []
    used_tier = 0
    seen = set(chosen_ids)
    for ti, tier in enumerate(tiers):
        if len(picked) >= need:
            break
        # 이 단계에서 해당 유형 & 아직 미선택인 후보
        cands = [
            q
            for q in tier
            if q.get("type") == qtype
            and q.get("id") not in seen
            and q.get("id") not in {p["id"] for p in picked}
        ]
        # 초급 모드: 고신뢰 라벨 우선. 부족하면 전체 허용.
        if beginner:
            hi = [q for q in cands if q.get("reliability") in HIGH_RELIABILITY]
            if len(hi) >= (need - len(picked)):
                cands = hi
        if not cands:
            continue
        weights = [weight(q, recent_ids) for q in cands]
        take = need - len(picked)
        got = weighted_sample_without_replacement(cands, weights, take, rng)
        picked.extend(got)
        used_tier = ti + 1
    return picked, len(picked), used_tier


# ---------------------------------------------------------------------------
# 출제 순서 배치 (설계 §3-3)
#   골격: (인성-오프닝) -> 공직가치 -> 직무 -> 지역현안 -> 상황형 -> ... -> 마무리
#   규칙: 동일 유형 3연속 금지, 상황형은 세션 중반 이후 배치.
# ---------------------------------------------------------------------------
def arrange_order(by_type):
    """by_type: {type: [questions]} -> 배치된 질문 리스트(각 항목에 phase 라벨 부여)."""
    buckets = {t: list(qs) for t, qs in by_type.items() if qs}
    total = sum(len(v) for v in buckets.values())
    sequence = []

    # 1) 오프닝: 인성 1문 (자기소개류) — 있으면 맨 앞
    if buckets.get("인성"):
        q = buckets["인성"].pop(0)
        sequence.append(("오프닝", q))

    midpoint = total / 2.0

    # 배치 선호 순위 (골격 흐름). 낮을수록 먼저.
    pref = {"공직가치": 0, "직무": 1, "지역현안": 2, "인성": 3, "상황형": 4}

    def remaining():
        return sum(len(v) for v in buckets.values())

    while remaining() > 0:
        pos = len(sequence)
        last_two = [t for t, _ in sequence[-2:]]
        # 후보 유형: 남아있고, 3연속 금지 위반 아님
        options = []
        for t, qs in buckets.items():
            if not qs:
                continue
            if len(last_two) == 2 and last_two[0] == last_two[1] == t:
                continue  # 동일 유형 3연속 금지
            # 상황형은 중반 이후에만
            if t == "상황형" and pos < midpoint:
                # 아직 다른 유형이 남아있으면 미룬다
                if any(qs2 for tt, qs2 in buckets.items() if tt != "상황형"):
                    continue
            options.append(t)
        if not options:
            # 3연속 제약으로 막혔으면 제약 완화(상황형 게이팅만 유지)
            for t, qs in buckets.items():
                if qs and not (t == "상황형" and pos < midpoint):
                    options.append(t)
            if not options:
                options = [t for t, qs in buckets.items() if qs]
        # 선호순위 + 남은 수 많은 것 우선 (군집 방지)
        options.sort(key=lambda t: (pref.get(t, 9), -len(buckets[t])))
        chosen_t = options[0]
        q = buckets[chosen_t].pop(0)
        phase = "상황형" if chosen_t == "상황형" else chosen_t
        sequence.append((phase, q))

    # 마무리(WRAPUP)는 질문 큐 외 고정 멘트이므로 골격 상 마지막에 라벨만 표시
    return sequence


# ---------------------------------------------------------------------------
# 메인 API
# ---------------------------------------------------------------------------
def select_questions(
    region,
    job,
    track="지방직표준",
    difficulty="실전",
    n_by_type=None,
    questions=None,
    recent_ids=None,
    seed=42,
):
    """
    질문 세트를 선택해 면접 순서로 정렬하여 반환.

    반환 dict:
      region, job, track, difficulty, quota, seq(list of {phase, question, tier}),
      diagnostics(유형별 충족/부족·완화단계)
    """
    if questions is None:
        questions = load_questions()
    if recent_ids is None:
        recent_ids = set()
    recent_ids = set(recent_ids)

    rng = random.Random(seed)

    # 쿼터 결정
    if n_by_type is not None:
        quota = dict(n_by_type)
    else:
        quota = dict(QUOTA_TRACKS.get(track, QUOTA_TRACKS["지방직표준"]))
        if track != "국가직9급" and region in QUOTA_REGION_OVERRIDE:
            quota = dict(QUOTA_REGION_OVERRIDE[region])

    exclude_regional = track == "국가직9급"
    beginner = difficulty == "초급"

    # 후보 풀 준비 + 중복 제거
    pool = dedupe(questions)
    tiers = build_tiered_candidates(pool, region, job, exclude_regional)

    by_type = {}
    diagnostics = {}
    chosen_ids = set()

    # 유형 처리 순서: 골격 우선순위대로 (재현성)
    type_order = ["인성", "공직가치", "직무", "지역현안", "상황형"]
    for qtype in type_order:
        need = quota.get(qtype, 0)
        if need <= 0:
            by_type[qtype] = []
            continue
        picked, got, used_tier = fill_type_quota(
            qtype, need, tiers, recent_ids, chosen_ids, rng, beginner
        )
        by_type[qtype] = picked
        chosen_ids.update(q["id"] for q in picked)
        diagnostics[qtype] = {
            "need": need,
            "got": got,
            "shortfall": need - got,  # >0 이면 LLM 생성 보충 대상
            "relaxed_to_tier": used_tier,  # 1=교차, 2=축분리, 3=common
        }

    # 순서 배치
    seq = arrange_order(by_type)

    # tier 라벨을 각 질문에 부착 (진단용)
    id_to_tier = {}
    for ti, tier in enumerate(tiers, start=1):
        for q in tier:
            id_to_tier.setdefault(q["id"], ti)

    seq_out = []
    for phase, q in seq:
        seq_out.append(
            {
                "phase": phase,
                "tier": id_to_tier.get(q["id"]),
                "question": q,
            }
        )

    return {
        "region": region,
        "job": job,
        "track": track,
        "difficulty": difficulty,
        "seed": seed,
        "quota": quota,
        "diagnostics": diagnostics,
        "seq": seq_out,
    }


# ---------------------------------------------------------------------------
# 출력 포매팅
# ---------------------------------------------------------------------------
_TIER_LABEL = {1: "지역+직렬", 2: "축분리", 3: "공통", None: "?"}


def format_result(result):
    lines = []
    lines.append("=" * 72)
    lines.append(
        f" 모의면접 질문 세트  |  {result['region']} · {result['job']} · "
        f"트랙={result['track']} · 난이도={result['difficulty']} · seed={result['seed']}"
    )
    lines.append("=" * 72)
    q = result["quota"]
    lines.append(
        "쿼터: "
        + "  ".join(f"{k}{v}" for k, v in q.items() if v)
        + f"  (합계 {sum(q.values())})"
    )
    lines.append("-" * 72)
    for i, item in enumerate(result["seq"], start=1):
        qq = item["question"]
        rel = qq.get("reliability") or "무라벨"
        yr = qq.get("year") or "미상"
        tier = _TIER_LABEL.get(item["tier"], "?")
        text = qq.get("text", "").replace("\n", " ")
        if len(text) > 60:
            text = text[:59] + "…"
        lines.append(
            f"{i:>2}. [{item['phase']:<5}] {text}"
        )
        lines.append(
            f"      └ id={qq['id']} type={qq.get('type')} "
            f"region={qq.get('region')} job={qq.get('job')} "
            f"신뢰도={rel} 연도={yr} 매칭={tier}"
        )
    lines.append(f"{len(result['seq'])+1:>2}. [마무리 ] 마지막으로 하고 싶은 말씀이 있으면 해 주세요. (WRAPUP)")
    lines.append("-" * 72)
    # 진단
    lines.append("진단 (유형별 충족 / 완화단계):")
    for t, d in result["diagnostics"].items():
        if d["need"] == 0:
            continue
        flag = ""
        if d["shortfall"] > 0:
            flag = f"  ⚠ 부족 {d['shortfall']}건 → LLM 생성 보충 대상(generated:true)"
        lines.append(
            f"  - {t}: {d['got']}/{d['need']}  "
            f"완화단계={_TIER_LABEL.get(d['relaxed_to_tier'])}{flag}"
        )
    lines.append("=" * 72)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="공무원 AI 모의면접 질문 선택 엔진 (프로토타입)"
    )
    ap.add_argument("--region", required=True, help="지자체명 (예: 서울특별시)")
    ap.add_argument("--job", required=True, help="직렬명 (예: 일반행정직)")
    ap.add_argument(
        "--track",
        default="지방직표준",
        choices=list(QUOTA_TRACKS.keys()),
        help="면접 트랙 (기본: 지방직표준)",
    )
    ap.add_argument(
        "--difficulty",
        default="실전",
        choices=["실전", "초급"],
        help="난이도 모드 (기본: 실전)",
    )
    ap.add_argument("--seed", type=int, default=42, help="랜덤 시드 (기본: 42)")
    ap.add_argument(
        "--questions",
        default=None,
        help="questions.json 경로 (기본: repo data/07-structured/questions.json)",
    )
    ap.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    args = ap.parse_args()

    questions = load_questions(args.questions)
    result = select_questions(
        region=args.region,
        job=args.job,
        track=args.track,
        difficulty=args.difficulty,
        questions=questions,
        seed=args.seed,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_result(result))


if __name__ == "__main__":
    main()
