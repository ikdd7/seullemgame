; ============================================================
;  OCR 진단 (폴더 자동탐색 방식) — 파일선택/드래그가 막힌 PC용
;  사용법:
;    1) 이 파일을 OCR.ahk 와 같은 폴더에 둔다.
;    2) 그 폴더 안에 시험할 PDF를 1개 복사해 넣는다(이름 아무거나).
;    3) 이 파일을 더블클릭한다.  → 폴더의 PDF를 자동으로 찾아 OCR.
;  ※ 파일 선택 창도, 드래그도 필요 없음.
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force
#Include OCR.ahk

; ── 같은 폴더에서 가장 최근 PDF 찾기 ──
pdf := "", newest := 0
Loop Files, A_ScriptDir "\*.pdf" {
    if (A_LoopFileTimeModified > newest)
        newest := A_LoopFileTimeModified, pdf := A_LoopFileFullPath
}

if (pdf = "") {
    MsgBox("이 폴더에 PDF가 없습니다.`n`n"
         . "시험할 스캔 PDF를 이 폴더에 복사해 넣고`n다시 더블클릭하세요.`n`n"
         . "현재 폴더:`n" A_ScriptDir, "PDF 없음", 48)
    ExitApp()
}
MsgBox("① 찾은 PDF:`n" pdf, "진단 1/4", 64)

; ── OCR 실행 ──
try {
    t0 := A_TickCount
    results := OCR.FromPDF(pdf, {lang: "ko"})
    sec := Round((A_TickCount - t0) / 1000, 1)
} catch as e {
    MsgBox("❌ OCR 실행 중 오류:`n`n"
         . "메시지: " e.Message "`n위치: " e.What "`n"
         . "추가: " (e.HasProp("Extra") ? e.Extra : "") "`n`n"
         . "이 창을 캡처해서 보내주세요.", "진단 - 오류", 16)
    ExitApp()
}

if (!IsObject(results) || results.Length = 0) {
    MsgBox("❌ OCR 결과가 비어 있습니다(페이지 0).", "진단 - 빈 결과", 48)
    ExitApp()
}
MsgBox("② OCR 완료. 페이지 " results.Length "개  (소요 " sec "초)", "진단 2/4", 64)

res := results[1]
raw := res.Text
MsgBox("③ 1페이지에서 읽은 글자(앞부분):`n`n"
     . (raw = "" ? "(아무 글자도 못 읽음!)" : SubStr(raw, 1, 600)),
       "진단 3/4 - 원본 OCR", 64)

wc := 0
for line in res.Lines
    for w in line.Words
        wc++
MsgBox("④ 인식된 단어 수: " wc "개`n`n③의 글자 내용을 캡처해서 보내주세요.", "진단 4/4 - 완료", 64)
ExitApp()
