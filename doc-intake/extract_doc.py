# -*- coding: utf-8 -*-
"""
소방 자체점검 관련 문서 → 문서접수 GUI 입력 필드 자동 추출기
────────────────────────────────────────────────────────────
대상 문서:
  · 소방시설등 자체점검 실시결과 보고서  (디지털 PDF: 텍스트 레이어 O)
  · 소방시설등의 자체점검 결과 이행계획서   (스캔 PDF)
  · 소방시설등의 자체점검 결과 이행완료 보고서 (스캔 PDF)

추출 흐름:
  1) PDF에 텍스트 레이어가 있으면  → PyMuPDF 좌표 기반 추출 (정확도 ~100%)
  2) 스캔(이미지)이면            → EasyOCR(ko) 좌표 기반 추출
  3) 대상물명 / 주소는 대상물DB.csv 와 유사도 매칭으로 자동 보정
     (예: OCR "변로로파크" → DB "뽀로로파크")

출력:
  · stdout : 보기 좋은 요약
  · --ini  PATH : AHK가 IniRead로 읽을 INI 파일
  · --json PATH : JSON 파일

사용:
  python extract_doc.py 문서.pdf
  python extract_doc.py 문서.pdf --ini out.ini
"""
import sys, os, re, json, argparse, difflib

# ── 선택 의존성 (있으면 사용) ───────────────────────────────
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

_READER = None
def get_reader():
    """EasyOCR Reader 지연 로딩 (최초 1회만)."""
    global _READER
    if _READER is None:
        import easyocr
        _READER = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
    return _READER

# 부서 후보 (관할 소방서). 필요 시 추가만 하면 됨.
FIRE_STATIONS = ["중부", "미추홀", "남동", "부평", "계양", "서부", "공단", "강화", "옹진"]
DEPT_SUFFIX = " 예방안전과"


# ════════════════════════════════════════════════════════════
#  공통 박스 모델: (x0, y0, x1, y1, text, conf)
# ════════════════════════════════════════════════════════════
def boxes_from_pdf_words(page):
    out = []
    for w in page.get_text("words"):
        out.append((w[0], w[1], w[2], w[3], w[4], 1.0))
    return out

def boxes_from_easyocr(img_path):
    res = get_reader().readtext(img_path, detail=1, paragraph=False)
    out = []
    for box, txt, conf in res:
        xs = [p[0] for p in box]; ys = [p[1] for p in box]
        out.append((min(xs), min(ys), max(xs), max(ys), txt, float(conf)))
    return out

def norm(s):
    return re.sub(r"\s+", "", s or "")

def find_label(boxes, label):
    """label(공백 무시)을 포함하는 첫 박스."""
    for b in boxes:
        if label in norm(b[4]):
            return b
    return None

def value_below(boxes, lab, x_left=-30, x_right=260, gap=2.4):
    """라벨 박스 '바로 아래 줄'의 값. x_left/x_right 는 라벨 x0 기준 오프셋."""
    if not lab:
        return ""
    lx0, ly0, lx1, ly1 = lab[0], lab[1], lab[2], lab[3]
    h = max(ly1 - ly0, 8)
    cand = [b for b in boxes
            if b[1] > ly0 + 0.4 * h                      # 라벨보다 아래
            and b[1] < ly1 + gap * h                     # 너무 멀지 않게
            and lx0 + x_left <= b[0] <= lx0 + x_right     # 같은 열
            and norm(b[4]) and not _is_label(b[4])]
    if not cand:
        return ""
    cand.sort(key=lambda b: (b[1], b[0]))
    y0 = cand[0][1]
    row = [b for b in cand if abs(b[1] - y0) <= 0.7 * h]
    row.sort(key=lambda b: b[0])
    return " ".join(b[4] for b in row).strip()

_LABEL_WORDS = ("명칭", "상호", "구분", "용도", "소재지", "특정소방", "대상물",
                "관계인", "소방안전관리자", "전화번호", "점검기간", "점검자", "성명")
def _is_label(t):
    n = norm(t)
    return any(w in n for w in _LABEL_WORDS)


# ════════════════════════════════════════════════════════════
#  필드 추출
# ════════════════════════════════════════════════════════════
def _classify(t):
    if "이행완료" in t:
        return "이행완료보고서"
    if "실시결과" in t or "결과보고서" in t:
        return "결과보고서"
    if "이행계획" in t:
        return "이행계획서"
    return ""

def detect_doc_type(title, full):
    # 제목 우선(본문 첨부서류 문구의 '이행계획서' 오인 방지), 없으면 본문 앞부분
    return _classify(norm(title)) or _classify(norm(full[:300])) or "미상"

def detect_status(full):
    f = norm(full)
    # 체크표시(√/✓/v) 가 작동/종합 중 어디 앞에 붙었는지
    if re.search(r"[\[\(［][√✓∨vV][\]\)］]?작동", f):
        return "작동"
    if re.search(r"[\[\(［][√✓∨vV][\]\)］]?종합", f):
        return "종합"
    if "작동점검" in f and "종합점검" not in f:
        return "작동"
    if "종합점검" in f and "작동점검" not in f:
        return "종합"
    return "작동"  # 기본값(대부분 작동점검)

def detect_dept(full):
    f = norm(full)
    for st in FIRE_STATIONS:
        if st + "소방서" in f:
            return st + "소방서" + DEPT_SUFFIX
    return ""

def detect_name(full):
    # OCR은 이름 글자 사이에 공백을 넣는 경우가 많음("김 철 곤") → 공백 허용, 최대 3음절
    for m in re.finditer(r"성\s*명[:：\s]*([가-힣](?:\s*[가-힣]){1,2})", full):
        cand = re.sub(r"\s", "", m.group(1))
        if len(cand) == 3 and cand[-1] in "전성번호명관소방":  # 뒷 단어 1글자 번짐 제거
            cand = cand[:2]
        if 2 <= len(cand) <= 4:
            return cand
    return ""

def detect_phone(full):
    m = re.search(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}", full)
    return re.sub(r"\s", "", m.group(0)) if m else ""

def extract_fields(boxes, full, title):
    lab_myeong = find_label(boxes, "명칭")
    lab_soje   = find_label(boxes, "소재지")
    building = value_below(boxes, lab_myeong, x_left=-30, x_right=230)
    addr     = value_below(boxes, lab_soje,   x_left=-20, x_right=900, gap=2.0)
    return {
        "doc_type": detect_doc_type(title, full),
        "building": norm(building),
        "addr":     re.sub(r"\s{2,}", " ", addr).strip(),
        "name":     detect_name(full),
        "phone":    detect_phone(full),
        "status":   detect_status(full),
        "dept":     detect_dept(full),
    }


# ════════════════════════════════════════════════════════════
#  대상물 DB 보정 (유사도 매칭)
# ════════════════════════════════════════════════════════════
def load_db(path):
    rows = []
    if not path or not os.path.exists(path):
        return rows
    import csv
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows

def correct_with_db(data, db):
    """OCR 대상물명을 DB와 유사도 매칭해 보정. 매칭되면 주소/부서도 DB 값으로 채움."""
    if not db or not data.get("building"):
        data["matched"] = ""
        return data
    names = [r.get("대상물명", "") for r in db]
    target = data["building"]
    best, score = None, 0.0
    for r in db:
        nm = r.get("대상물명", "")
        if not nm:
            continue
        s = difflib.SequenceMatcher(None, target, nm).ratio()
        if s > score:
            best, score = r, s
    if best and score >= 0.5:
        data["building"] = best["대상물명"]
        if best.get("주소"):
            data["addr"] = best["주소"]
        if best.get("부서"):
            data["dept"] = best["부서"]
        data["matched"] = f"{best['대상물명']} (유사도 {score:.0%})"
    else:
        data["matched"] = f"미매칭 (최고 유사도 {score:.0%})"
    return data


# ════════════════════════════════════════════════════════════
#  메인
# ════════════════════════════════════════════════════════════
def get_title(doc):
    best, sz = "", 0
    for b in doc[0].get_text("dict").get("blocks", []):
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                if sp["size"] > sz and len(sp["text"].strip()) > 3:
                    sz, best = sp["size"], sp["text"]
    return best

def process(path, db_path=None):
    if fitz is None:
        return {"error": "PyMuPDF(fitz) 미설치 → pip install pymupdf"}
    doc = fitz.open(path)
    has_text = any(len(p.get_text().strip()) > 30 for p in doc)

    if has_text:
        page = doc[0] if len(doc[0].get_text().strip()) > 30 else max(doc, key=lambda p: len(p.get_text()))
        boxes = boxes_from_pdf_words(page)
        full = "\n".join(p.get_text() for p in doc)
        title = get_title(doc)
        data = extract_fields(boxes, full, title)
        data["source"] = "digital"
    else:
        # 스캔: 머리말 표가 있는 첫 페이지만 OCR (속도)
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3))
        img = path + ".p0.png"
        pix.save(img)
        try:
            boxes = boxes_from_easyocr(img)
        finally:
            if os.path.exists(img):
                os.remove(img)
        full = " ".join(b[4] for b in boxes)
        data = extract_fields(boxes, full, full[:200])
        data["source"] = "ocr"

    data = correct_with_db(data, load_db(db_path))
    return data


FIELDS = ["doc_type", "building", "addr", "name", "phone", "status", "dept", "source", "matched"]
LABELS = {"doc_type": "문서종류", "building": "대상물명", "addr": "주소", "name": "관계인",
          "phone": "전화번호", "status": "점검종류", "dept": "부서",
          "source": "추출방식", "matched": "DB매칭"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--db", default=os.path.join(os.path.dirname(__file__), "대상물DB.csv"))
    ap.add_argument("--ini")
    ap.add_argument("--json")
    args = ap.parse_args()

    data = process(args.pdf, args.db)

    if "error" in data:
        print("⚠ " + data["error"])
        sys.exit(1)

    print("─" * 40)
    for k in FIELDS:
        print(f"  {LABELS[k]:6s}: {data.get(k,'')}")
    print("─" * 40)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    if args.ini:
        # AHK가 FileRead(..,"UTF-8")로 안전하게 읽도록 BOM 포함 UTF-8
        with open(args.ini, "w", encoding="utf-8-sig") as f:
            f.write("[doc]\n")
            for k in FIELDS:
                f.write(f"{k}={data.get(k,'')}\n")

if __name__ == "__main__":
    main()
