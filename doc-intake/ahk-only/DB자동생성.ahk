; ============================================================
;  대상물DB 자동생성
;  - 스캔 폴더의 기존 파일명 "…(대상물명).pdf" 들에서 대상물명을 모아
;    대상물DB.csv 를 자동으로 만든다. (기존 주소/부서는 보존)
;  - 이 DB가 있으면, 새 스캔의 OCR이 한두 글자 틀려도 정확히 교정됨.
;  - OCR.ahk 와 같은 폴더에 두고 더블클릭. (※ 새 스캔 파일명 자동변경과는 별개)
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force

global SCAN_FOLDER := "C:\Users\User\Desktop\scan"
dbPath := A_ScriptDir "\대상물DB.csv"

; ── 기존 DB 읽기 (주소/부서 보존) ──
existing := Map()
if FileExist(dbPath) {
    i := 0
    Loop Parse FileRead(dbPath, "UTF-8"), "`n", "`r" {
        i++
        if (i = 1 || A_LoopField = "")
            continue
        c := ParseCSVLine(A_LoopField)
        nm := (c.Length >= 1) ? Trim(c[1]) : ""
        if (nm != "")
            existing[nm] := { addr: (c.Length >= 2 ? Trim(c[2]) : ""),
                              dept: (c.Length >= 3 ? Trim(c[3]) : "") }
    }
}

if !DirExist(SCAN_FOLDER) {
    MsgBox("스캔 폴더를 찾을 수 없습니다:`n" SCAN_FOLDER, "오류", 16)
    ExitApp()
}

; ── 파일명에서 (대상물명) 수집 ──
order := []          ; 순서 유지
seen  := Map()
added := 0, skipped := 0
Loop Files, SCAN_FOLDER "\*.pdf" {
    SplitPath(A_LoopFileName, , , , &noext)
    if RegExMatch(noext, "\(([^()]+)\)[^()]*$", &m) {
        nm := Trim(m[1])
        if (nm != "" && !seen.Has(nm)) {
            seen[nm] := true
            order.Push(nm)
            added++
        }
    } else {
        skipped++
    }
}

; ── 기존에만 있던 이름도 유지 ──
for nm in existing
    if !seen.Has(nm)
        order.Push(nm), seen[nm] := true

; ── 저장 ──
out := "대상물명,주소,부서`n"
for nm in order {
    a := existing.Has(nm) ? existing[nm].addr : ""
    d := existing.Has(nm) ? existing[nm].dept : ""
    out .= QuoteCSV(nm) "," QuoteCSV(a) "," QuoteCSV(d) "`n"
}
fobj := FileOpen(dbPath, "w", "UTF-8")     ; BOM 포함 → 메모장/엑셀에서 한글 안 깨짐
fobj.Write(out)
fobj.Close()

; ── CSV 유틸 ──
ParseCSVLine(line) {
    fields := [], cur := "", inQ := false
    i := 1, n := StrLen(line)
    while (i <= n) {
        ch := SubStr(line, i, 1)
        if (inQ) {
            if (ch = '"') {
                if (SubStr(line, i + 1, 1) = '"') {
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

QuoteCSV(s) {
    if (InStr(s, ",") || InStr(s, '"') || InStr(s, "`n") || InStr(s, "`r")) {
        s := StrReplace(s, '"', '""')
        return '"' s '"'
    }
    return s
}

MsgBox("대상물DB.csv 를 만들었습니다.`n`n"
     . "· 등록된 대상물: " order.Length "개`n"
     . "· 파일명에 (대상물명) 없어서 건너뜀: " skipped "개`n`n"
     . "저장 위치:`n" dbPath "`n`n"
     . "※ 주소/부서를 채워두면 더 정확해지지만, 비워둬도 대상물명 교정은 됩니다.",
       "DB 생성 완료", 64)
ExitApp()
