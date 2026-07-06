#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_context.py

data/03-regions/*.md (지역) 와 data/04-jobs/*.md (직렬) 마크다운을
AI 질문 생성 프롬프트에 바로 주입할 수 있는 구조화 JSON으로 변환한다.

- 지역: {region, 면접방식요약, 시정비전, 슬로건, 핵심사업[], 지역현안[], source}
- 직렬: {job, 개요, 주요업무[], 법령키워드[], 핵심제도[], source}

배치 파일(경기도-주요시군 / 군단위-* / 광역시-자치구 / 특수채용 / 국가직 등)은
헤딩(H1/H2)별로 개별 지역·직렬로 분해한다.

표준 라이브러리만 사용. 마크다운 원본은 수정하지 않는다(읽기 전용).
휴리스틱 파싱이므로 완벽하지 않으며, 핵심 필드 위주로 안정적 추출을 목표로 한다.
"""

import os
import re
import json

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION_DIR = os.path.join(BASE, "data", "03-regions")
JOB_DIR = os.path.join(BASE, "data", "04-jobs")
OUT_DIR = os.path.join(BASE, "data", "07-structured")

# 지역: 단일 지역이 아니라 참고/총론 성격이라 지역 엔트리를 만들지 않는 파일
REGION_SKIP_FILES = {
    "지자체-인재상-슬로건.md",
    "지자체-통계-팩트시트.md",
    "서울특별시-심화.md",  # 서울특별시.md 와 중복 → 스킵
}

# ---------------------------------------------------------------------------
# 마크다운 파싱 유틸
# ---------------------------------------------------------------------------
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")


def parse_headings(text):
    """헤딩 목록을 반환. 각 항목: {level, title, line, body(list of str)}."""
    lines = text.splitlines()
    heads = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            heads.append({"level": len(m.group(1)), "title": m.group(2).strip(), "line": i})
    for idx, h in enumerate(heads):
        nxt = heads[idx + 1]["line"] if idx + 1 < len(heads) else len(lines)
        h["body"] = lines[h["line"] + 1:nxt]
    return heads, lines


def block_subheads(heads, i):
    """heads[i] 헤딩의 하위 블록(더 깊은 레벨의 헤딩들)을 반환."""
    lvl = heads[i]["level"]
    subs = []
    for j in range(i + 1, len(heads)):
        if heads[j]["level"] <= lvl:
            break
        subs.append(heads[j])
    return subs


def bullets_of(body_lines):
    out = []
    for ln in body_lines:
        m = BULLET_RE.match(ln)
        if m:
            out.append(m.group(1).strip())
    return out


def strip_md(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)  # 링크 → 텍스트
    s = s.replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", s).strip()


QUOTE_RE = re.compile(r"[“\"'‘「『]([^”\"'’」』\n]{2,60})[”\"'’」』]")


def first_quote(s):
    m = QUOTE_RE.search(s)
    return m.group(1).strip() if m else None


def bold_label(bullet):
    """- **라벨**: ...  형태에서 라벨을 추출."""
    m = re.match(r"\s*\*\*(.+?)\*\*", bullet)
    if m:
        return m.group(1).strip()
    return None


def short_topic(bullet):
    """불릿을 짧은 토픽 문자열로 요약(굵은 라벨 우선, 없으면 첫 절)."""
    lbl = bold_label(bullet)
    if lbl:
        return strip_md(lbl)
    t = strip_md(bullet)
    t = re.split(r"[.\(—:：·]|\s-\s", t)[0].strip()
    return t[:45]


def split_terms(s):
    """쉼표/슬래시(괄호 밖)로 항목 분해. 괄호 안 쉼표는 보존."""
    s = strip_md(s)
    out, buf, depth = [], [], 0
    for ch in s:
        if ch in "([{（［":
            depth += 1
            buf.append(ch)
        elif ch in ")]}）］":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch in ",，/" and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    res = []
    for t in out:
        t = t.strip(" ·-–—")
        if len(t) >= 2 and not t.isdigit():
            res.append(t)
    return res


def clean_heading(title):
    """헤딩에서 선두 'N.'/'N)' 번호와 괄호주석을 제거."""
    t = title.strip()
    t = re.sub(r"^\d+\s*[.)]\s*", "", t)
    t = re.sub(r"[（(][^）)]*[）)]", "", t)  # 괄호 주석 제거
    t = re.sub(r"[⚠️★※]+", "", t)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------------------
# 지역 파서
# ---------------------------------------------------------------------------
_REGION_STOP = ["공무원", "면접", "자료", "공통", "주제", "질문", "구조", "현안",
                "팁", "가이드", "총괄", "기준", "변화", "복구", "배치", "컨텍스트",
                "정책", "비전", "활용", "특성", "유형", "상황", "포인트", "차이",
                "개요", "방식", "카드", "암기", "가지"]


def is_region_heading(title):
    t = clean_heading(title)
    if not t:
        return False
    if any(w in t for w in _REGION_STOP):
        return False
    core = t.split()[-1] if " " in t else t
    if not re.search(r"[시군구도]$", core):
        return False
    return 2 <= len(core) <= 7


def region_name_from_h1(h1):
    t = h1
    for w in ["공무원", "면접 자료", "면접", "자료"]:
        t = t.replace(w, " ")
    t = re.sub(r"[（(][^）)]*[）)]", "", t)  # (심화) 등 제거
    t = re.sub(r"[—\-]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


VISION_KW = ["비전", "슬로건", "기조", "포지셔닝", "구상"]
MAYOR_KW = ["시장", "군수", "지사", "도지사", "구청장"]


def _section_kind(title):
    t = title
    if "질문" in t or "기출" in t:  # 예상/복원 질문 섹션은 컨텍스트 아님
        return set()
    kinds = set()
    if "면접" in t and any(k in t for k in ["방식", "개요", "형식", "특징"]):
        kinds.add("interview")
    if any(k in t for k in ["비전", "정책", "사업", "프로젝트", "공약", "컨텍스트",
                            "도정", "시정", "군정", "현안", "상황"]):
        kinds.add("context")
    if "현안" in t:
        kinds.add("issue")
    if any(k in t for k in ["사업", "정책", "프로젝트", "공약", "비전"]):
        kinds.add("policy")
    return kinds


def slogan_from(text):
    """'슬로건' 뒤 인용구를 우선, 없으면 첫 인용구."""
    m = re.search(r"슬로건[^“\"'‘「『]{0,6}[“\"'‘「『]([^”\"'’」』\n]{2,40})", text)
    if m:
        return m.group(1).strip()
    return first_quote(text)


def extract_region(name, subheads, direct_bullets, source):
    interview_summary = ""
    vision = ""
    slogan = ""
    policies, issues = [], []
    seen_p, seen_i = set(), set()

    noise = {"기타", "그늘", "목표", "참고", "비고", "빛과 그늘", "특징", "현안"}

    def add_p(t):
        t = t.strip(" ·-–—.")
        if t and len(t) >= 2 and t not in seen_p and t not in noise:
            seen_p.add(t)
            policies.append(t)

    def add_i(t):
        t = t.strip(" ·-–—.")
        if t and len(t) >= 2 and t not in seen_i and t not in noise:
            seen_i.add(t)
            issues.append(t)

    for sh in subheads:
        kinds = _section_kind(sh["title"])
        bl = bullets_of(sh["body"])
        if not bl:
            continue

        if "interview" in kinds and not interview_summary:
            parts = [strip_md(b) for b in bl[:2]]
            interview_summary = " / ".join(p for p in parts if p)[:320]

        if "context" not in kinds:
            continue

        is_issue = "issue" in kinds
        is_policy = "policy" in kinds
        combined = is_issue and is_policy       # 예: "시정 비전·핵심 사업·지역 현안"
        dedicated_issue = is_issue and not is_policy

        for b in bl:
            label = bold_label(b) or ""
            text = strip_md(b)
            head = text[:30]
            value = re.split(r"[:：]", b, 1)[-1] if (":" in b or "：" in b) else ""
            is_mayor = any(k in label for k in MAYOR_KW)
            is_vision = any(k in (label + head) for k in VISION_KW)
            is_issue_bullet = any(k in label for k in ["현안", "과제"])

            if is_mayor:
                q = slogan_from(text)
                if q and not slogan:
                    slogan = q
                if not vision:
                    vision = text[:220]
                continue
            if is_vision:
                if not vision or len(vision) > 200:
                    vision = text[:220]
                q = slogan_from(text)
                if q:
                    slogan = q  # 비전 줄의 슬로건이 인물 줄보다 우선
                continue

            if dedicated_issue:
                add_i(short_topic(b))
            elif combined and is_issue_bullet:
                items = split_terms(value) if value else []
                if len(items) >= 2:
                    for it in items:
                        add_i(it)
                else:
                    add_i(short_topic(b))
            elif is_policy:
                add_p(short_topic(b))

    # 폴백: 비전이 비었으면 어느 섹션이든 인물(시장/지사/군수) 줄에서 확보
    if not vision:
        for sh in subheads:
            for b in bullets_of(sh["body"]):
                if any(k in (bold_label(b) or "") for k in MAYOR_KW):
                    vision = strip_md(b)[:220]
                    q = slogan_from(strip_md(b))
                    if q and not slogan:
                        slogan = q
                    break
            if vision:
                break

    if not slogan and vision:
        slogan = slogan_from(vision) or ""

    return {
        "region": name,
        "면접방식요약": interview_summary,
        "시정비전": vision,
        "슬로건": slogan,
        "핵심사업": policies[:15],
        "지역현안": issues[:15],
        "source": source,
    }


def parse_region_file(path):
    fname = os.path.basename(path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    heads, _ = parse_headings(text)
    if not heads:
        return []
    h1 = heads[0]["title"]

    # 배치 파일 여부: 지역명 헤딩(레벨 1~2)이 2개 이상
    region_idx = [i for i, h in enumerate(heads)
                  if h["level"] in (1, 2) and i != 0 and is_region_heading(h["title"])]

    results = []
    if len(region_idx) >= 2:
        for i in region_idx:
            name = clean_heading(heads[i]["title"])
            subs = block_subheads(heads, i)
            rec = extract_region(name, subs, bullets_of(heads[i]["body"]), fname)
            results.append(rec)
        return results

    # 단일 지역 파일
    if fname in REGION_SKIP_FILES:
        return []
    name = region_name_from_h1(h1)
    subs = [h for h in heads[1:]]  # H1 제외 모든 하위 섹션
    rec = extract_region(name, subs, [], fname)
    # 핵심 컨텍스트가 전무하면 스킵(참고성 파일 방어)
    if not rec["시정비전"] and not rec["핵심사업"] and not rec["지역현안"]:
        return []
    results.append(rec)
    return results


# ---------------------------------------------------------------------------
# 직렬 파서
# ---------------------------------------------------------------------------
_JOB_STOP = ["개요", "질문", "방식", "기출", "현안", "키워드", "출처", "공통",
             "차이", "구조", "특징", "상황형", "전문", "정책", "복원", "조직",
             "직무", "특화", "업무", "역량", "부서", "이론", "분야"]


def is_job_heading(title):
    t = clean_heading(title)  # 번호·괄호 주석 제거 후 판정
    if not t or len(t) > 12:
        return False
    if any(w in t for w in _JOB_STOP):
        return False
    return bool(re.search(r"(직|관|원|군무원|수사)$", t))


def job_name_from_h1(h1):
    t = h1
    for w in ["공무원", "면접 자료", "면접", "자료"]:
        t = t.replace(w, " ")
    t = re.sub(r"[—\-]\s*$", "", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\(\s+", "(", t).replace(" )", ")").replace("()", "")
    return t.strip(" —-")


def _is_law_term(term):
    core = re.sub(r"[（(][^）)]*[）)]\s*$", "", term).strip()
    return bool(re.search(r"(법|법률|률|규칙|조례|협약|령|규정|훈령|고시|헌장|지침)$", core))


def extract_job(name, sections, source):
    overview = ""
    duties = []
    laws, systems = [], []
    seen_d, seen_l, seen_s = set(), set(), set()

    duty_bullets = []
    overview_bullets = []
    law_bullets = []

    for sh in sections:
        title = sh["title"]
        bl = bullets_of(sh["body"])
        if "주요 업무" in title or (title.strip() in ("업무",)):
            duty_bullets = bl
        elif "개요" in title:
            overview_bullets = bl
            # 개요 안에 라벨형 '주요 업무:' 불릿이 있을 수 있음(배치 파일)
            for b in bl:
                lab = bold_label(b) or ""
                head_txt = b.split(":", 1)[0].split("：", 1)[0]
                if ("주요 업무" in lab or "업무" in head_txt[:8]) and not duty_bullets:
                    val = b.split(":", 1)[-1] if ":" in b else b.split("：", 1)[-1]
                    duty_bullets = split_terms(val)
        if "법령" in title or "특화 키워드" in title:
            law_bullets.extend(bl)

    # 주요 업무
    for b in duty_bullets:
        t = strip_md(b)
        if t and t not in seen_d:
            seen_d.add(t)
            duties.append(t)

    # 개요 요약: 특성/성격/소속 라벨 우선, 없으면 주요업무 앞 2개
    desc_parts = []
    for b in overview_bullets:
        lab = bold_label(b) or ""
        head_txt = b.split(":", 1)[0].split("：", 1)[0]
        if any(k in (lab + head_txt) for k in ["특성", "성격", "소속", "개요", "특징"]):
            desc_parts.append(strip_md(b))
    if not desc_parts:
        desc_parts = duties[:2]
    overview = " / ".join(p for p in desc_parts if p)[:320]

    # 법령·제도
    for b in law_bullets:
        lab = bold_label(b) or ""
        head = b.split(":", 1)[0].split("：", 1)[0]
        low = lab + head
        val = b
        if ":" in b or "：" in b:
            val = re.split(r"[:：]", b, 1)[-1]
        terms = split_terms(val)
        if "법령" in low and "제도" not in low:
            for t in terms:
                if t not in seen_l:
                    seen_l.add(t)
                    laws.append(t)
        elif any(k in low for k in ["제도", "용어", "키워드"]):
            for t in terms:
                if len(t) <= 40 and t not in seen_s:  # 문장형 프로즈 배제
                    seen_s.add(t)
                    systems.append(t)
        else:
            # 라벨 없는 혼합 불릿 → 항목별 분류(법령명은 길어도 유지, 제도는 짧게)
            for t in terms:
                if _is_law_term(t):
                    if t not in seen_l:
                        seen_l.add(t)
                        laws.append(t)
                elif len(t) <= 40:
                    if t not in seen_s:
                        seen_s.add(t)
                        systems.append(t)

    return {
        "job": name,
        "개요": overview,
        "주요업무": duties[:15],
        "법령키워드": laws[:60],
        "핵심제도": systems[:80],
        "source": source,
    }


def parse_job_file(path):
    fname = os.path.basename(path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    heads, _ = parse_headings(text)
    if not heads:
        return []
    h1 = heads[0]["title"]

    job_idx = [i for i, h in enumerate(heads)
               if h["level"] == 2 and is_job_heading(h["title"])]

    results = []
    if len(job_idx) >= 2:
        for i in job_idx:
            name = clean_heading(heads[i]["title"])
            subs = block_subheads(heads, i)
            results.append(extract_job(name, subs, fname))
    else:
        # 단일 직렬 파일
        name = job_name_from_h1(h1)
        subs = [h for h in heads[1:]]
        results.append(extract_job(name, subs, fname))

    # 핵심 필드가 전무한 엔트리는 제외(참고성/변형 구조 파일 방어)
    return [r for r in results
            if r["개요"] or r["주요업무"] or r["법령키워드"] or r["핵심제도"]]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    regions = []
    for fn in sorted(os.listdir(REGION_DIR)):
        if fn.endswith(".md"):
            regions.extend(parse_region_file(os.path.join(REGION_DIR, fn)))

    jobs = []
    for fn in sorted(os.listdir(JOB_DIR)):
        if fn.endswith(".md"):
            jobs.extend(parse_job_file(os.path.join(JOB_DIR, fn)))

    with open(os.path.join(OUT_DIR, "region_context.json"), "w", encoding="utf-8") as f:
        json.dump(regions, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, "job_context.json"), "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    print("지역 엔트리: %d개" % len(regions))
    print("직렬 엔트리: %d개" % len(jobs))
    return regions, jobs


if __name__ == "__main__":
    main()
