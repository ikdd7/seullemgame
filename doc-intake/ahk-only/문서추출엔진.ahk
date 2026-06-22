; ============================================================
;  문서추출엔진 (AutoHotkey v2 전용 - Python 불필요)
;  Windows 내장 OCR(OCR.ahk: Windows.Media.Ocr)로 PDF를 읽어
;  문서접수 필드(대상물명/주소/관계인/전화/작동·종합/부서)를 추출.
;  대상물DB.csv 유사도 매칭으로 OCR 오타 자동 보정.
;
;  핵심 함수:  ExtractFromPDF(pdfPath, dbPath) → Map
; ============================================================
#Requires AutoHotkey v2.0
#Include OCR.ahk

global FIRE_STATIONS := ["중부", "미추홀", "남동", "부평", "계양", "서부", "공단", "강화", "옹진"]
global LABEL_WORDS   := ["명칭", "상호", "구분", "용도", "소재지", "특정소방", "대상물",
                         "관계인", "소방안전관리자", "전화번호", "점검기간", "점검자", "성명"]

; ── 메인: PDF → 추출 결과 Map ───────────────────────────────
ExtractFromPDF(pdfPath, dbPath := "") {
    ; 1) 한국어 OCR 설치 확인
    avail := OCR.GetAvailableLanguages()
    koLang := ""
    for tag in StrSplit(avail, "`n", "`r")
        if (InStr(tag, "ko") && Trim(tag) != "") {
            koLang := Trim(tag)
            break
        }
    if (koLang = "")
        throw Error("이 PC에 '한국어 OCR'이 설치되어 있지 않습니다.`n`n"
            . "[설정] → [시간 및 언어] → [언어 및 지역] → 한국어 →`n"
            . "[⋯] → [언어 옵션] → [광학 문자 인식(OCR)] 설치 후 다시 시도하세요.`n`n"
            . "현재 사용 가능한 OCR 언어:`n" avail)

    ; 2) 1페이지 OCR (scale=2: 인식률 향상)
    results := OCR.FromPDF(pdfPath, {lang: koLang, scale: 2})
    res := results[1]
    words := ParseWords(res)
    full := res.Text

    ; 3) 위치 기반 + 정규식 추출
    data := Map()
    data["doc_type"] := DetectDocType(full)

    labMyeong := FindLabel(words, "명칭")
    labSoje   := FindLabel(words, "소재지")
    labGubun  := FindLabel(words, "구분")              ; 우측 '구분(용도)' 열 경계
    rightEdge := IsObject(labGubun) ? labGubun.x - 5 : 100000000

    bx := IsObject(labMyeong) ? labMyeong.x - 30 : 0
    data["building"] := NoSpace(ValueBelow(words, labMyeong, bx, rightEdge, 2.6))
    ax := IsObject(labSoje) ? labSoje.x - 20 : 0
    data["addr"]     := CleanSpace(ValueBelow(words, labSoje, ax, 100000000, 2.2))
    data["name"]     := DetectName(full)
    data["phone"]    := DetectPhone(full)
    data["status"]   := DetectStatus(full)
    data["dept"]     := DetectDept(full)
    data["source"]   := "ocr"

    ; 4) 대상물 DB 보정
    CorrectWithDB(data, dbPath)
    return data
}

; ── OCR 결과 → 평면 단어 배열 [{t,x,y,w,h}, ...] ────────────
ParseWords(res) {
    words := []
    for line in res.Lines
        for w in line.Words
            words.Push({t: w.Text, x: w.x, y: w.y, w: w.w, h: w.h})
    return words
}

; ── 라벨(부분일치) 박스 찾기 ────────────────────────────────
FindLabel(words, sub) {
    for w in words
        if InStr(NoSpace(w.t), sub)
            return w
    return ""
}

; ── 라벨 바로 아래 줄(같은 열)의 값 ─────────────────────────
ValueBelow(words, lab, xMin, xMax, gap := 2.5) {
    if !IsObject(lab)
        return ""
    h := Max(lab.h, 8)
    cand := []
    for w in words {
        if (w.y > lab.y + 0.4 * h
            && w.y < (lab.y + lab.h) + gap * h
            && w.x >= xMin && w.x <= xMax
            && Trim(w.t) != "" && !IsLabelWord(w.t))
            cand.Push(w)
    }
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

SortByX(arr) {                       ; 삽입 정렬 (x 오름차순)
    Loop arr.Length - 1 {
        i := A_Index + 1
        key := arr[i]
        j := i - 1
        while (j >= 1 && arr[j].x > key.x) {
            arr[j + 1] := arr[j]
            j--
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

; ── 정규식 기반 필드 ────────────────────────────────────────
DetectDocType(full) {
    f := NoSpace(SubStr(full, 1, 300))
    if InStr(f, "이행완료")
        return "이행완료보고서"
    if (InStr(f, "실시결과") || InStr(f, "결과보고서"))
        return "결과보고서"
    if InStr(f, "이행계획")
        return "이행계획서"
    return "미상"
}

DetectName(full) {
    if RegExMatch(full, "성\s*명[:：\s]*([가-힣](?:\s*[가-힣]){1,2})", &m) {
        n := NoSpace(m[1])
        if (StrLen(n) = 3 && InStr("전성번호명관방소", SubStr(n, 3, 1)))
            n := SubStr(n, 1, 2)         ; 뒷 단어 1글자 번짐 제거
        return n
    }
    if RegExMatch(full, "관계인[^가-힣]{0,6}([가-힣]{2,3})", &m2)
        return m2[1]
    return ""
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
    return "작동"        ; 기본값(대부분 작동점검)
}

DetectDept(full) {
    f := NoSpace(full)
    for st in FIRE_STATIONS
        if InStr(f, st "소방서")
            return st "소방서 예방안전과"
    return ""
}

; ── 대상물 DB 유사도 보정 ───────────────────────────────────
CorrectWithDB(data, dbPath) {
    data["matched"] := ""
    if (dbPath = "" || !FileExist(dbPath) || data["building"] = "")
        return
    txt := FileRead(dbPath, "UTF-8")
    target := data["building"]
    best := "", bestCols := "", bestScore := 0.0
    idx := 0
    Loop Parse txt, "`n", "`r" {
        idx++
        line := A_LoopField
        if (line = "" || idx = 1)        ; 헤더 스킵
            continue
        cols := StrSplit(line, ",")
        nm := (cols.Length >= 1) ? Trim(cols[1]) : ""
        if (nm = "")
            continue
        s := Similarity(target, nm)
        if (s > bestScore)
            bestScore := s, best := nm, bestCols := cols
    }
    if (best != "" && bestScore >= 0.5) {
        data["building"] := best
        if (IsObject(bestCols) && bestCols.Length >= 2 && Trim(bestCols[2]) != "")
            data["addr"] := Trim(bestCols[2])
        if (IsObject(bestCols) && bestCols.Length >= 3 && Trim(bestCols[3]) != "")
            data["dept"] := Trim(bestCols[3])
        data["matched"] := best " (유사도 " Round(bestScore * 100) "%)"
    } else {
        data["matched"] := "미매칭 (최고 " Round(bestScore * 100) "%)"
    }
}

; ── 문자열 유사도(편집거리 기반) ────────────────────────────
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
        i := A_Index
        cur := [i]
        Loop n {
            j := A_Index
            cost := (SubStr(s, i, 1) = SubStr(t, j, 1)) ? 0 : 1
            cur.Push(Min(cur[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        }
        prev := cur
    }
    return prev[n + 1]
}

; ── 문자열 유틸 ─────────────────────────────────────────────
NoSpace(s)    => RegExReplace(s, "\s", "")
CleanSpace(s) => Trim(RegExReplace(s, "\s{2,}", " "))
