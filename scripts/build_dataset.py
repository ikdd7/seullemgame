#!/usr/bin/env python3
"""공무원 면접 질문 데이터셋 빌더.

data/02-common, data/03-regions, data/04-jobs 아래의 마크다운 파일에서
면접 질문 불릿을 추출해 data/07-structured/questions.json 으로 저장한다.

표준 라이브러리만 사용. 마크다운 원본은 수정하지 않는다.

사용법:
    python3 scripts/build_dataset.py
"""

import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = DATA_DIR / "07-structured"
OUT_FILE = OUT_DIR / "questions.json"

# 질문을 추출할 디렉토리 → category 매핑.
# (01/05/06 디렉토리는 평가기준·데이터셋 조사·답변 가이드 문서라 질문 불릿이 없다)
CATEGORY_BY_DIR = {
    "02-common": "common",
    "03-regions": "region",
    "04-jobs": "job",
}

# ---------------------------------------------------------------- 태그 어휘

RELIABILITY_RULES = [
    # (정규식, 정규화 값) — 앞의 것이 우선순위 높음
    (re.compile(r"확인"), "확인"),
    (re.compile(r"복원"), "복원"),
    (re.compile(r"기출"), "기출"),
    (re.compile(r"예상|대비"), "예상"),
    (re.compile(r"빈출|단골|압박"), "빈출"),
]
RELIABILITY_ORDER = ["확인", "복원", "기출", "예상", "빈출"]

TYPE_RULES = [
    (re.compile(r"상황"), "상황형"),
    (re.compile(r"공직가치|공직관|국가관|윤리관|^공직$|공직"), "공직가치"),
    (re.compile(r"5분|발표|스피치|토의"), "발표"),
    (re.compile(r"지역현안|현안|지역상식|시정|도정|정책|^지역$"), "지역현안"),
    (re.compile(r"인성|경험"), "인성"),
    (re.compile(r"직무|직렬|실무|전공"), "직무"),
    (re.compile(r"시사"), "시사"),
    (re.compile(r"후속"), "후속"),
]

# 짧은 지역명 → 공식 명칭
REGION_NORMALIZE = {
    "서울": "서울특별시", "서울시": "서울특별시",
    "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시",
    "세종": "세종특별자치시", "경기": "경기도", "경기도": "경기도",
    "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도",
    "경북": "경상북도", "경남": "경상남도", "제주": "제주특별자치도",
}

# 태그 안에 등장할 수 있는 직렬명 → 정규화(04-jobs 파일명 기준)
JOB_NORMALIZE = {
    "일반행정": "일반행정직", "일반행정직": "일반행정직", "행정직": "일반행정직",
    "세무": "세무직", "세무직": "세무직",
    "교육행정": "교육행정직", "교육행정직": "교육행정직", "교행": "교육행정직",
    "사회복지": "사회복지직", "사회복지직": "사회복지직",
    "전산": "전산직", "전산직": "전산직",
    "토목": "토목직", "토목직": "토목직",
    "건축": "건축직", "건축직": "건축직",
    "기계": "기계직", "기계직": "기계직",
    "전기": "전기직", "전기직": "전기직",
    "환경": "환경직", "환경직": "환경직",
    "농업": "농업직", "농업직": "농업직",
    "간호": "간호직", "간호직": "간호직",
    "보건": "보건직", "보건직": "보건직",
    "사서": "사서직", "사서직": "사서직",
    "교정": "교정직", "교정직": "교정직",
    "소방": "소방직", "지적": "지적직", "고용노동": "고용노동직",
    "검찰": "검찰직", "출입국": "출입국관리직", "관세": "관세직",
    "통계": "통계직", "우정": "우정직", "경찰": "경찰직",
}

YEAR_RE = re.compile(r"(19|20)\d{2}")

# ---------------------------------------------------------------- 라인 판별

BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s")
LEADING_TAG_RE = re.compile(r"^\[([^\[\]]{1,60})\]\s*")
TRAILING_TAG_RE = re.compile(r"\s*\[([^\[\]]{1,40})\]\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
BOLD_LABEL_RE = re.compile(r"^\*\*([^*]{1,40})\*\*\s*$")
URL_RE = re.compile(r"https?://")
IMPERATIVE_END_RE = re.compile(r"(보라|하라|하시오|시오|말하라|해보시오)[.)\s]*$")

# 태그는 있으나 물음표가 없는 불릿 중, 해설·후기성 문장을 걸러내는 어미 블랙리스트
COMMENTARY_END_RE = re.compile(
    r"(다|됨|음|함|임|평|것|존재|제한|참조|필요|적용|언급|확인|미확인|전함|후기|중"
    r"|권장|유지|공개|상이|다수|계열|빈출|제시문|참고용|주류|암기)\s*[.。]?\s*$"
)
# 태그 성분에 이런 단어가 있으면 질문이 아니라 메모/후기
NON_QUESTION_TAG_RE = re.compile(r"후기|참고용|출처")
# 본문(끝 괄호 제거 후)에 이런 표지가 있으면 출처 안내/해설 → 물음표가 있어도 제외
COMMENTARY_MARKER_RE = re.compile(
    r"게시글|게시판|열람|복기|원문|수험가|학원가|참고용|디시인사이드|okpass|다음카페|후기"
)
# 질문 뒤에 붙는 편집 주석 ("— 연결 공직가치: …", "— 쟁점: …", "— 청렴성·전문성" 등)
ANNOTATION_TAIL_RES = [
    re.compile(r"\s*[—–]+\s*(연결\s*공직가치|쟁점|유형)\s*:\s*.*$"),
    re.compile(r"\s*[—–]+\s*[가-힣·(),\s]{2,40}$"),
]
# 문두의 "(세무직)" 류 직렬 표시 괄호
LEADING_PAREN_RE = re.compile(r"^\(([^()]{2,25})\)\s*")


def strip_trailing_paren(text: str) -> str:
    """끝부분의 괄호 주석( (…)·(→ …) 등 )을 반복 제거한 문자열 반환 (판별용)."""
    t = text.strip()
    while True:
        m = re.search(r"\([^()]*\)\s*[.。]?\s*$", t)
        if not m or m.start() == 0:
            return t
        t = t[: m.start()].strip()


def strip_markdown(text: str) -> str:
    """굵게/기울임 마커 제거, 공백 정리."""
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    t = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    return unicodedata.normalize("NFC", t)


# ---------------------------------------------------------------- 태그 파싱


def parse_tag_components(raw_tag: str):
    """'[2021/공통/지역현안]' 류 태그 문자열을 (year, region, job, qtype, reliability)로 분해."""
    year = region = job = qtype = reliability = None
    for comp in (c.strip() for c in raw_tag.split("/")):
        if not comp:
            continue
        # 연도
        m = YEAR_RE.search(comp)
        if m and year is None:
            year = int(m.group(0))
        # 신뢰도
        for rx, value in RELIABILITY_RULES:
            if rx.search(comp):
                if reliability is None or (
                    RELIABILITY_ORDER.index(value) < RELIABILITY_ORDER.index(reliability)
                ):
                    reliability = value
                break
        # 지역
        for key, full in REGION_NORMALIZE.items():
            if comp == key or comp.startswith(key + "시") or comp == full:
                if region is None:
                    region = full
                break
        # 직렬
        for key, full in JOB_NORMALIZE.items():
            if comp == key or comp == full:
                if job is None:
                    job = full
                break
        # 유형
        if qtype is None:
            for rx, value in TYPE_RULES:
                if rx.search(comp):
                    qtype = value
                    break
    return year, region, job, qtype, reliability


def infer_type_from_context(*contexts: str):
    """파일명·섹션 제목 등 문맥 문자열에서 질문 유형 추론."""
    for ctx in contexts:
        if not ctx:
            continue
        for rx, value in TYPE_RULES:
            if rx.search(ctx):
                return value
    return None


CITY_HEADING_RE = re.compile(r"^([가-힣]{1,8}(시|군|구))\b")


def region_from_filename(stem: str, current_h2: str):
    if stem == "경기도-주요시군":
        base = "경기도"
    elif stem == "비수도권-주요시군":
        base = None
    else:
        base = stem
    # 주요시군 파일은 H2 제목(수원시, 천안시 …)이 더 구체적
    if stem.endswith("주요시군") and current_h2:
        m = CITY_HEADING_RE.match(strip_markdown(current_h2))
        if m:
            return m.group(1)
    return base


# ---------------------------------------------------------------- 본 추출


def is_question_candidate(text: str, has_tag: bool, tag_raw: str) -> bool:
    """불릿 본문이 질문(또는 발표 주제)인지 판별."""
    if URL_RE.search(text):
        return False
    if has_tag and NON_QUESTION_TAG_RE.search(tag_raw or ""):
        return False
    core = strip_trailing_paren(strip_markdown(text))
    # 출처 안내·복기 메모 등은 물음표가 있어도 질문이 아님
    if COMMENTARY_MARKER_RE.search(core):
        return False
    if "?" in core:
        return True
    if IMPERATIVE_END_RE.search(core):
        return True
    if has_tag:
        # 태그는 있지만 물음표 없는 경우: 해설/후기성 문장 어미면 제외
        if COMMENTARY_END_RE.search(core):
            return False
        return True
    return False


def extract_from_file(path: Path, category: str):
    stem = path.stem
    rel_path = str(path.relative_to(ROOT))
    questions = []
    current_h2 = ""
    current_section = ""  # 가장 최근의 하위 헤딩(h2~h4) 또는 굵은 라벨
    in_source_section = False

    default_job = stem.split("-")[0] if category == "job" else None
    # 파일명 기반 기본 유형 (02-common 전용 파일들)
    file_type = infer_type_from_context(stem)

    for line in path.read_text(encoding="utf-8").splitlines():
        hm = HEADING_RE.match(line)
        if hm:
            title = hm.group(2).strip()
            level = len(hm.group(1))
            if level <= 2:
                current_h2 = title
            current_section = title
            in_source_section = bool(re.search(r"출처|참고\s*자료|출전", title))
            continue
        bm = BOLD_LABEL_RE.match(line.strip())
        if bm:
            current_section = bm.group(1)
            continue
        if in_source_section:
            continue
        mb = BULLET_RE.match(line)
        if not mb or CHECKBOX_RE.match(line):
            continue

        body = mb.group(1).strip()
        tag_raw = None
        mt = LEADING_TAG_RE.match(body)
        if mt:
            tag_raw = mt.group(1).strip()
            body = body[mt.end():].strip()
        trailing_tags = []
        while True:
            mt2 = TRAILING_TAG_RE.search(body)
            if not mt2:
                break
            trailing_tags.append(mt2.group(1).strip())
            body = body[: mt2.start()].strip()

        all_tag = "/".join(filter(None, [tag_raw] + trailing_tags))

        text = strip_markdown(body)
        # "— 연결 공직가치: …" / "— 쟁점: …" 류 편집 주석 꼬리 제거
        for rx in ANNOTATION_TAIL_RES:
            stripped = rx.sub("", text).strip()
            if len(stripped) >= 15:
                text = stripped

        # 문두 "(세무직)" 류 직렬 표기 추출
        paren_job = None
        paren_year = None
        mp = LEADING_PAREN_RE.match(text)
        if mp:
            inner = mp.group(1)
            for key, full in JOB_NORMALIZE.items():
                if key in inner:
                    paren_job = full
                    break
            my = YEAR_RE.search(inner)
            if my:
                paren_year = int(my.group(0))
            if paren_job:
                text = text[mp.end():].strip()

        if not is_question_candidate(text, bool(all_tag), all_tag):
            continue
        if len(text) < 8:  # 파편 제거
            continue

        year, tag_region, tag_job, tag_type, reliability = parse_tag_components(all_tag)
        year = year or paren_year

        region = tag_region
        if category == "region":
            region = region_from_filename(stem, current_h2) or tag_region
        job = tag_job or paren_job or default_job
        if tag_job == "공통":
            job = paren_job or default_job
        # 기타직렬.md 는 H2 제목이 실제 직렬명 (운전직, 시설관리직 …)
        if stem == "기타직렬":
            mh = re.match(r"^([가-힣]{2,10}직)", strip_markdown(current_h2))
            if mh:
                job = mh.group(1)
        qtype = tag_type or infer_type_from_context(current_section, current_h2) or file_type

        questions.append(
            {
                "text": text,
                "category": category,
                "region": region,
                "job": job,
                "year": year,
                "type": qtype,
                "reliability": reliability,
                "source_file": rel_path,
            }
        )
    return questions


def main():
    all_questions = []
    files_scanned = []
    for dirname, category in sorted(CATEGORY_BY_DIR.items()):
        for path in sorted((DATA_DIR / dirname).glob("*.md")):
            qs = extract_from_file(path, category)
            files_scanned.append({"file": str(path.relative_to(ROOT)), "questions": len(qs)})
            all_questions.extend(qs)

    # 동일 파일 내 완전 중복 제거
    seen = set()
    deduped = []
    for q in all_questions:
        key = (q["text"], q["source_file"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)

    for i, q in enumerate(deduped, start=1):
        q_id = f"q{i:05d}"
        deduped[i - 1] = {"id": q_id, **q}

    def dist(field):
        c = Counter(q[field] or "(없음)" for q in deduped)
        return dict(sorted(c.items(), key=lambda kv: -kv[1]))

    meta = {
        "name": "korean-civil-service-interview-questions",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/build_dataset.py",
        "source_dirs": sorted(CATEGORY_BY_DIR.keys()),
        "total_questions": len(deduped),
        "files_scanned": files_scanned,
        "distributions": {
            "category": dist("category"),
            "type": dist("type"),
            "reliability": dist("reliability"),
            "region": dist("region"),
            "job": dist("job"),
            "year": dict(
                sorted(Counter(str(q["year"] or "(미상)") for q in deduped).items())
            ),
        },
        "schema": {
            "id": "고유 ID (q00001 형식, 파일 정렬 순서 기반)",
            "text": "질문/발표주제 본문 (마크다운 마커 제거, NFC 정규화)",
            "category": "common | region | job (원본 디렉토리 기반)",
            "region": "지역명 (03-regions 파일명 또는 태그 기반, 없으면 null)",
            "job": "직렬명 (04-jobs 파일명 또는 태그 기반, 없으면 null)",
            "year": "출제(복원) 연도 정수, 미상이면 null",
            "type": "공직가치 | 인성 | 직무 | 지역현안 | 상황형 | 시사 | 발표 | 후속 | null",
            "reliability": "확인 | 복원 | 기출 | 예상 | 빈출 | null (원본 태그 기반)",
            "source_file": "리포지토리 루트 기준 원본 마크다운 경로",
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps({"meta": meta, "questions": deduped}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # ------------------------------------------------------------ 통계 출력
    print(f"총 질문 수: {len(deduped)}  (중복 제거 전 {len(all_questions)})")
    print(f"출력 파일: {OUT_FILE.relative_to(ROOT)}")
    for field, label in [
        ("category", "카테고리"),
        ("type", "질문 유형"),
        ("reliability", "신뢰도"),
        ("region", "지역"),
        ("job", "직렬"),
    ]:
        print(f"\n[{label}별 분포]")
        for k, v in dist(field).items():
            print(f"  {k}: {v}")
    print("\n[파일별 추출 수]")
    for f in files_scanned:
        print(f"  {f['file']}: {f['questions']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
