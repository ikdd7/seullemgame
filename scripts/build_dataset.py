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
# 번호 목록(1. / 2) …)도 질문 항목으로 인식 — 군 단위·심화 파일이 번호 목록을 씀
NUMBERED_RE = re.compile(r"^\s*\d{1,3}[.)]\s+(.*)$")
CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s")
LEADING_TAG_RE = re.compile(r"^\[([^\[\]]{1,60})\]\s*")
TRAILING_TAG_RE = re.compile(r"\s*\[([^\[\]]{1,40})\]\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
BOLD_LABEL_RE = re.compile(r"^\*\*([^*]{1,40})\*\*\s*$")
URL_RE = re.compile(r"https?://")
IMPERATIVE_END_RE = re.compile(r"(보라|하라|하시오|시오|말하라|해보시오)[.)\s\"'”’]*$")

# 태그는 있으나 물음표가 없는 불릿 중, 해설·후기성 문장을 걸러내는 어미 블랙리스트
COMMENTARY_END_RE = re.compile(
    r"(다|됨|음|함|임|평|것|존재|제한|참조|필요|적용|언급|확인|미확인|전함|후기|중"
    r"|권장|유지|공개|상이|다수|계열|빈출|제시문|참고용|주류|암기|이룸|배치|부여"
    r"|평가|생략|진행|재개|대상|유효|개선|강화|변경|시행|도입|주제|질문|질의응답"
    r"|보도|일괄|통용|화제|작용|추세|강조|가능|방식)\s*[.。]?\s*[\"'”’]?\s*$"
)
# 태그 성분에 이런 단어가 있으면 질문이 아니라 메모/후기
NON_QUESTION_TAG_RE = re.compile(r"후기|참고용|출처|분위기|운영|결과")
# 본문(괄호 제거 후)에 이런 표지가 있으면 출처 안내/해설 → 물음표가 있어도 제외
COMMENTARY_MARKER_RE = re.compile(
    r"게시글|게시판|열람 필요|열람 권장|열람이 제한|직접 열람|복기|원문|수험가|학원가"
    r"|참고용|디시인사이드|okpass|다음카페|후기|합격생 조언|응시자 조언|\.md|상세는"
)
# 면접 형식·평정 설명 불릿의 머리말 (질문이 아님)
META_PREFIX_RE = re.compile(
    r"^(평정|판정|진행|현행|구조|구성|형식|절차|소요 시간|면접관|개별면접,"
    r"|결과 결정|특징|준비 팁|출제 경향|사전조사서|평가 포인트|평가 관전|신규 확인"
    r"|민선 \d+기|시정 비전|집단토의 연혁|3분 스피치|참고\s*:|원문\s*:|입실|대기장|면접 \d)"
)
# 본문 끝의 출처성 괄호 주석 ("(법률저널 보도)", "(합격 후기 기반)" 등)
CITATION_PAREN_RE = re.compile(
    r"\s*\([^()]*(후기|복기|보도|스니펫|카페|갤러리|기반|언론|나무위키|더쿠|위키)[^()]*\)\s*[.。]?\s*$"
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


def clean_core(text: str) -> str:
    """판별용 코어 텍스트: 마크다운 마커·모든 괄호 구간 제거, 공백 정리."""
    t = strip_markdown(text)
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"\([^()]*\)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


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


# H2 제목에서 "1. 천안시 (충남)" → "천안시" 형태로 시·군·구명 추출
CITY_HEADING_RE = re.compile(r"([가-힣]{2,8}(?:특별자치시|특별자치도|광역시|특별시|시|군|구))")

# 파일명 자체가 행정구역이 아니라 수집 배치 라벨인 파일들
# → 지역값은 파일명이 아니라 H2 제목의 실제 시·군·구명에서 뽑는다.
BATCH_STEM_RE = re.compile(
    r"(주요시군|잔여시군|3차시군|추가시군|중소시군|군단위|자치구)"
)


def region_from_filename(stem: str, current_h2: str):
    is_batch = bool(BATCH_STEM_RE.search(stem))
    if stem == "경기도-주요시군":
        base = "경기도"
    elif is_batch:
        base = None  # 배치 파일은 파일명을 지역값으로 쓰지 않음
    else:
        # "서울특별시-심화", "부산광역시-2차" 등 접미사를 벗겨 본 지역명으로
        base = re.sub(r"-(심화|\d+차|상세|보강).*$", "", stem)
        base = REGION_NORMALIZE.get(base, base)
    # 배치 파일은 H2 제목(수원시, 천안시, 강남구 …)이 실제 지역
    if is_batch and current_h2:
        m = CITY_HEADING_RE.search(strip_markdown(current_h2))
        if m:
            return m.group(1)
    return base


# ---------------------------------------------------------------- 본 추출


def is_question_candidate(text: str, has_tag: bool, tag_raw: str) -> bool:
    """불릿 본문이 질문(또는 발표 주제)인지 판별."""
    if URL_RE.search(text):
        return False
    core = clean_core(text)
    # 출처 안내·복기 메모 등은 물음표가 있어도 질문이 아님 (괄호 속 인용 표기는 무시)
    if COMMENTARY_MARKER_RE.search(core):
        return False
    # 강한 질문 신호: 물음표 / 명령형 어미
    if "?" in core or "？" in core:
        return True
    if IMPERATIVE_END_RE.search(core):
        return True
    # "평정요소: …", "판정: 우수/보통/미흡" 등 형식 설명 불릿 제외
    if META_PREFIX_RE.match(core):
        return False
    # "질문1 / 질문2 / …" 형태의 복원 질문 목록
    if text.count(" / ") >= 2:
        return True
    if not has_tag:
        return False
    # 괄호를 걷어낸 알맹이가 너무 짧으면 라벨성 항목 ("(…주제 일괄)" 등)
    if len(core) < 8:
        return False
    # 태그는 있지만 물음표 없는 경우: 출처성 태그·해설성 어미면 제외
    if NON_QUESTION_TAG_RE.search(tag_raw or ""):
        return False
    if COMMENTARY_END_RE.search(core):
        return False
    return True


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
        if mb and CHECKBOX_RE.match(line):
            continue
        if not mb:
            mb = NUMBERED_RE.match(line)
        if not mb:
            continue

        body = mb.group(1).strip()
        body = re.sub(r"^[★☆]\S*\s+", "", body)  # "★신규 [태그] …" 프리픽스
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

        # "[확인 — 스티마 카페 후기]" / "[확인: 나무위키]" 류 출처 꼬리 제거
        cleaned_tags = [
            re.sub(r"\s*[—:].*$", "", t).strip() for t in [tag_raw] + trailing_tags if t
        ]
        all_tag = "/".join(filter(None, cleaned_tags))

        text = strip_markdown(body)
        # "— 연결 공직가치: …" / "— 쟁점: …" 류 편집 주석 꼬리 제거
        for rx in ANNOTATION_TAIL_RES:
            stripped = rx.sub("", text).strip()
            if len(stripped) >= 15:
                text = stripped
        # "(법률저널 보도)" 류 출처성 괄호 꼬리 제거
        while True:
            stripped = CITATION_PAREN_RE.sub("", text).strip()
            if stripped == text or len(stripped) < 10:
                break
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
        if year is None:
            # "2019 일반행정·우정: …" 처럼 본문이 연도로 시작하는 경우
            mty = re.match(r"^(20\d{2})\b", text)
            if mty:
                year = int(mty.group(1))
        if year is None:
            # "## 2025년", "### 2022년" 같은 연도 섹션 하위의 질문
            for ctx in (current_section, current_h2):
                mh_year = re.match(r"^(20\d{2})\s*년", ctx or "")
                if mh_year:
                    year = int(mh_year.group(1))
                    break

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
        # 지역 파일에서 유형이 안 잡히면 대개 지역현안 질문(시·군 현안 특화)
        if qtype is None and category == "region":
            qtype = "지역현안"

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
