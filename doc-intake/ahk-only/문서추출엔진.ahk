; ============================================================
;  문서추출엔진 (AutoHotkey v2 전용 - Python 불필요)
;  Windows 내장 OCR(OCR.ahk)로 PDF를 읽어 문서접수 필드를 추출.
;
;  ★ 대상물명은 'OCR 전체 글자 ↔ 대상물DB' 유사도 매칭으로 찾음.
;    → OCR이 칸을 잘못 집거나 한두 글자 틀려도 DB에서 정확히 교정.
;    (예: OCR '인성물류참고' → DB '인성물류창고')
;
;  핵심 함수:  ExtractFromPDF(pdfPath, dbPath) → Map
; ============================================================
#Requires AutoHotkey v2.0
#Include OCR.ahk

global FIRE_STATIONS := ["중부", "미추홀", "남동", "부평", "계양", "서부", "공단", "강화", "옹진"]
global LABEL_WORDS   := ["명칭", "상호", "구분", "용도", "소재지", "특정소방", "대상물",
                         "관계인", "소방안전관리자", "전화번호", "점검기간", "점검자", "성명"]

ExtractFromPDF(pdfPath, dbPath := "") {
    ; 1) 한국어 OCR 확인
    avail := OCR.GetAvailableLanguages()
    koLang := ""
    for tag in StrSplit(avail, "`n", "`r")
        if (InStr(tag, "ko") && Trim(tag) != "") {
            koLang := Trim(tag)
            break
        }
    if (koLang = "")
        throw Error("이 PC에 '한국어 OCR'이 설치되어 있지 않습니다.`n`n"
            . "[설정]→[시간 및 언어]→[언어 및 지역]→한국어→[언어 옵션]에서 OCR 설치 후 재시도.")

    ; 2) 1페이지 OCR
    res   := OCR.FromPDF(pdfPath, {lang: koLang, scale: 2})[1]
    words := ParseWords(res)
    full  := res.Text

    data := Map()
    data["doc_type"] := DetectDocType(full)
    data["name"]     := DetectName(full)
    data["phone"]    := DetectPhone(full)
    data["status"]   := DetectStatus(full)
    data["source"]   := "ocr"

    ; 위치 기반(보조) 추출값
    labMyeong := FindLabel(words, "명칭")
    labSoje   := FindLabel(words, "소재지")
    labGubun  := FindLabel(words, "구분")
    rightEdge := IsObject(labGubun) ? labGubun.x - 5 : 100000000
    bx := IsObject(labMyeong) ? labMyeong.x - 30 : 0
    ax := IsObject(labSoje)   ? labSoje.x - 20   : 0
    ocrBuilding := CleanBuilding(NoSpace(ValueBelow(words, labMyeong, bx, rightEdge, 2.6)))
    ocrAddr     := CleanSpace(ValueBelow(words, labSoje, ax, 100000000, 2.2))
    ocrDept     := DetectDept(full)

    ; 3) 대상물명 결정
    ;   ① OCR이 읽은 명칭값(ocrBuilding)이 DB 이름과 가까우면 → 그 DB 이름으로 교정
    ;      (정상 칸을 읽은 경우의 오타 교정. 약한 매칭이 정답을 덮어쓰지 않음)
    ;   ② 그게 아니면(칸을 잘못 집었을 수 있음) → 본문 전체 슬라이딩 매칭, 단 높은 임계(0.8)
    ;   ③ 둘 다 아니면 → OCR이 읽은 명칭값 그대로
    db := LoadDB(dbPath)
    chosen := "", cscore := 0.0
    fs := BestNameMatch(ocrBuilding, db)
    if (ocrBuilding != "" && IsObject(fs) && fs.score >= 0.6) {
        chosen := fs, cscore := fs.score
    } else {
        sl := BestDBMatch(full, db)
        if (IsObject(sl) && sl.score >= 0.8)
            chosen := sl, cscore := sl.score
    }
    if (IsObject(chosen)) {
        data["building"] := chosen.name
        data["addr"]     := (chosen.addr != "") ? chosen.addr : ocrAddr
        data["dept"]     := (chosen.dept != "") ? chosen.dept : ocrDept
        data["matched"]  := chosen.name " (유사도 " Round(cscore * 100) "%)"
    } else {
        data["building"] := ocrBuilding
        data["addr"]     := ocrAddr
        data["dept"]     := ocrDept
        data["matched"]  := (db.Length ? "DB미매칭(OCR값 사용)" : "DB 비어있음")
    }
    return data
}

; ── OCR 결과 → 평면 단어 배열 ───────────────────────────────
ParseWords(res) {
    words := []
    for line in res.Lines
        for w in line.Words
            words.Push({t: w.Text, x: w.x, y: w.y, w: w.w, h: w.h})
    return words
}

FindLabel(words, sub) {
    for w in words
        if InStr(NoSpace(w.t), sub)
            return w
    return ""
}

ValueBelow(words, lab, xMin, xMax, gap := 2.5) {
    if !IsObject(lab)
        return ""
    h := Max(lab.h, 8)
    cand := []
    for w in words
        if (w.y > lab.y + 0.4 * h && w.y < (lab.y + lab.h) + gap * h
            && w.x >= xMin && w.x <= xMax && Trim(w.t) != "" && !IsLabelWord(w.t))
            cand.Push(w)
    if !cand.Length
        return ""
    minY := cand[1].y
    for w in cand
        if (w.y < minY)
            minY := w.y
    row := []
    for w in cand
        if (Abs(w.y - minY) <= 0.7 * h)
            row.Push(w)
    SortByX(row)
    out := ""
    for w in row
        out .= w.t " "
    return Trim(out)
}

SortByX(arr) {
    Loop arr.Length - 1 {
        i := A_Index + 1, key := arr[i], j := i - 1
        while (j >= 1 && arr[j].x > key.x) {
            arr[j + 1] := arr[j], j--
        }
        arr[j + 1] := key
    }
}

IsLabelWord(t) {
    n := NoSpace(t)
    for w in LABEL_WORDS
        if InStr(n, w)
            return true
    return false
}

; ── 정규식 필드 ─────────────────────────────────────────────
DetectDocType(full) {
    f := NoSpace(SubStr(full, 1, 300))
    if InStr(f, "이행완료")                      ; 이행 먼저 판별
        return "이행완료보고서"
    if InStr(f, "이행계획")
        return "이행계획서"
    ; 이행 문서가 아니면서 자체점검/실시결과 → 실시결과(자체점검) 보고서
    if (InStr(f, "실시결과") || InStr(f, "결과보고서") || InStr(f, "자체점검"))
        return "결과보고서"
    return "미상"
}

DetectName(full) {
    ; OCR이 한 곳에서 이름을 깨뜨려도(예: 관계인 '성준=' ) 다른 곳의 '성준현'을 살림.
    ; 여러 후보를 모아 '가장 많이/길게' 나온 이름을 선택.
    counts := Map()
    _AddNameCands(full, "성\s*명\s*[:：(]\s*([가-힣](?:\s*[가-힣]){1,2})", counts)  ; 성명: 이름
    _AddNameCands(full, "([가-힣](?:\s*[가-힣]){1,2})\s*서\s*명", counts)            ; 이름 서명
    best := _PickName(counts)
    if (best != "")
        return best
    ; 폴백: 성명 뒤 느슨하게
    if RegExMatch(full, "성\s*명\s*[:：(]?\s*([가-힣](?:\s*[가-힣]){1,2})", &m) {
        n := NoSpace(m[1])
        return (StrLen(n) = 3 && SubStr(n, 3, 1) = "전") ? SubStr(n, 1, 2) : n
    }
    return ""
}

_AddNameCands(s, rx, counts) {
    pos := 1
    while (pos := RegExMatch(s, rx, &m, pos)) {
        n := NoSpace(m[1])
        if (StrLen(n) = 3 && SubStr(n, 3, 1) = "전")     ; '…전화' 번짐 → 2음절
            n := SubStr(n, 1, 2)
        if (StrLen(n) >= 2 && StrLen(n) <= 3)
            counts[n] := (counts.Has(n) ? counts[n] : 0) + 1
        pos += Max(StrLen(m[0]), 1)
    }
}

_PickName(counts) {
    b3 := "", c3 := 0, b2 := "", c2 := 0           ; 3음절 우선, 그 안에서 최다 빈도
    for nm, cnt in counts {
        if (StrLen(nm) = 3) {
            if (cnt > c3)
                c3 := cnt, b3 := nm
        } else if (cnt > c2)
            c2 := cnt, b2 := nm
    }
    return (b3 != "") ? b3 : b2
}

DetectPhone(full) {
    if RegExMatch(full, "01[016789][-\s]?\d{3,4}[-\s]?\d{4}", &m)
        return RegExReplace(m[0], "\s", "")
    return ""
}

DetectStatus(full) {
    f := NoSpace(full)
    if RegExMatch(f, "[\[\(［][√✓∨vV][\]\)］]?작동")
        return "작동"
    if RegExMatch(f, "[\[\(［][√✓∨vV][\]\)］]?종합")
        return "종합"
    if (InStr(f, "종합점검") && !InStr(f, "작동점검"))
        return "종합"
    return "작동"
}

DetectDept(full) {
    f := NoSpace(full)
    for st in FIRE_STATIONS
        if InStr(f, st "소방서")
            return st "소방서 예방안전과"
    return ""
}

; ── 대상물 DB 로드 → [{name,addr,dept}, ...] ────────────────
LoadDB(dbPath) {
    db := []
    if (dbPath = "" || !FileExist(dbPath))
        return db
    txt := FileRead(dbPath, "UTF-8")
    i := 0
    Loop Parse txt, "`n", "`r" {
        i++
        line := A_LoopField
        if (line = "" || i = 1)            ; 헤더 스킵
            continue
        c := ParseCSVLine(line)            ; 쉼표 포함 이름(따옴표) 처리
        nm := (c.Length >= 1) ? Trim(c[1]) : ""
        if (nm = "")
            continue
        db.Push({name: nm,
                 addr: (c.Length >= 2 ? Trim(c[2]) : ""),
                 dept: (c.Length >= 3 ? Trim(c[3]) : "")})
    }
    return db
}

; ── CSV 한 줄 파싱 (따옴표로 감싼 쉼표 포함 필드 지원) ───────
ParseCSVLine(line) {
    fields := [], cur := "", inQ := false
    i := 1, n := StrLen(line)
    while (i <= n) {
        ch := SubStr(line, i, 1)
        if (inQ) {
            if (ch = '"') {
                if (SubStr(line, i + 1, 1) = '"') {   ; "" → 따옴표 1개
                    cur .= '"', i += 2
                    continue
                }
                inQ := false, i++
            } else
                cur .= ch, i++
        } else if (ch = '"')
            inQ := true, i++
        else if (ch = ",")
            fields.Push(cur), cur := "", i++
        else
            cur .= ch, i++
    }
    fields.Push(cur)
    return fields
}

; ── OCR 명칭값 ↔ DB 이름 '풀스트링' 유사도 최고 항목 ────────
BestNameMatch(target, db) {
    if (target = "" || !db.Length)
        return ""
    best := "", bs := 0.0
    for row in db {
        s := Similarity(target, row.name)
        if (s > bs)
            bs := s, best := row
    }
    if IsObject(best)
        return {name: best.name, addr: best.addr, dept: best.dept, score: bs}
    return ""
}

; ── OCR 전체 글자에서 DB 이름과 가장 잘 맞는 항목 찾기 ──────
BestDBMatch(full, db) {
    if !db.Length
        return ""
    f := SubStr(NoSpace(full), 1, 400)     ; 대상물명은 표 상단부 → 검색범위 제한(속도)
    flen := StrLen(f)
    best := "", bestScore := 0.0
    for row in db {
        L := StrLen(row.name)
        if (L < 2)
            continue
        for dl in [0, -1, 1] {                 ; 윈도우 길이 L-1 ~ L+1
            wl := L + dl
            if (wl < 2 || wl > flen)
                continue
            Loop (flen - wl + 1) {
                s := Similarity(row.name, SubStr(f, A_Index, wl))
                if (s > bestScore) {
                    bestScore := s, best := row
                    if (bestScore >= 0.99)
                        break
                }
            }
            if (bestScore >= 0.99)
                break
        }
        if (bestScore >= 0.99)
            break
    }
    if IsObject(best)
        return {name: best.name, addr: best.addr, dept: best.dept, score: bestScore}
    return ""
}

; ── 문자열 유사도(편집거리) ─────────────────────────────────
Similarity(a, b) {
    la := StrLen(a), lb := StrLen(b)
    if (la = 0 && lb = 0)
        return 1.0
    maxl := Max(la, lb)
    return maxl ? (1.0 - Levenshtein(a, b) / maxl) : 0.0
}

Levenshtein(s, t) {
    m := StrLen(s), n := StrLen(t)
    if (m = 0)
        return n
    if (n = 0)
        return m
    prev := []
    Loop n + 1
        prev.Push(A_Index - 1)
    Loop m {
        i := A_Index, cur := [i]
        Loop n {
            j := A_Index
            cost := (SubStr(s, i, 1) = SubStr(t, j, 1)) ? 0 : 1
            cur.Push(Min(cur[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        }
        prev := cur
    }
    return prev[n + 1]
}

NoSpace(s)    => RegExReplace(s, "\s", "")
CleanSpace(s) => Trim(RegExReplace(s, "\s{2,}", " "))
; 대상물명 OCR 노이즈(앞뒤 기호 등) 제거 → 한글/영숫자/()/-/, 만 남김
CleanBuilding(s) => RegExReplace(s, "[^가-힣A-Za-z0-9()\-,]", "")
