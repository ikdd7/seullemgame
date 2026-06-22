; ============================================================
;  좌표 진단 — 표의 '명칭/용도/소재지'를 OCR이 어떻게 읽었는지 본다.
;  스캔 폴더의 최신 PDF 상단부 단어들을 좌표와 함께 보여준다.
;  OCR.ahk 와 같은 폴더에 두고 더블클릭.
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force
#Include OCR.ahk

global SCAN_FOLDER := "C:\Users\User\Desktop\scan"

pdf := "", newest := 0
Loop Files, SCAN_FOLDER "\*.pdf"
    if (A_LoopFileTimeModified > newest)
        newest := A_LoopFileTimeModified, pdf := A_LoopFileFullPath
if (pdf = "") {
    MsgBox("스캔 폴더에 PDF가 없습니다:`n" SCAN_FOLDER, "PDF 없음", 48)
    ExitApp()
}

try
    res := OCR.FromPDF(pdf, {lang: "ko"})[1]
catch as e {
    MsgBox("OCR 오류: " e.Message, "오류", 16)
    ExitApp()
}

; ── 단어 수집 + 페이지 높이 추정 ──
words := []
maxY := 1
for line in res.Lines
    for w in line.Words {
        words.Push({t: w.Text, x: Round(w.x), y: Round(w.y)})
        if (w.y > maxY)
            maxY := w.y
    }

; ── 상단부(표 머리말, y < 45%) 만, y→x 순 정렬 ──
top := []
for w in words
    if (w.y < maxY * 0.45)
        top.Push(w)
Loop top.Length - 1 {           ; 정렬 (y, x)
    i := A_Index + 1, key := top[i], j := i - 1
    while (j >= 1 && (top[j].y > key.y || (top[j].y = key.y && top[j].x > key.x))) {
        top[j + 1] := top[j], j--
    }
    top[j + 1] := key
}

out := ""
for w in top
    out .= "y=" w.y "`tx=" w.x "`t" w.t "`n"

SplitPath(pdf, &fname)
txt := A_ScriptDir "\OCR좌표.txt"
try FileDelete(txt)
FileAppend("[" fname "]`n`n" out, txt, "UTF-8")
try Run('notepad.exe "' txt '"')

MsgBox("상단부 단어 " top.Length "개를 OCR좌표.txt 에 저장했고 메모장으로 열었습니다.`n`n"
     . "그 메모장 내용(또는 이 창)을 캡처해서 보내주세요.`n`n"
     . SubStr(out, 1, 1500), "좌표 진단", 64)
ExitApp()
