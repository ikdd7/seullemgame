; ============================================================
;  OCR 진단 (드래그 앤 드롭 방식)
;  - 파일 선택 창이 안 뜨는 PC용.
;  - 사용법: PDF 파일을 마우스로 집어서 이 .ahk 아이콘 위에 떨어뜨린다.
;    (더블클릭 X →  PDF를 끌어다 놓기 O)
;  - OCR.ahk 와 같은 폴더에 둘 것.
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force
#Include OCR.ahk

; ── 드래그로 넘어온 파일이 없으면 안내 ──
if (A_Args.Length < 1) {
    MsgBox("📌 사용법`n`n"
         . "1) PDF 파일을 마우스로 '집어서'`n"
         . "2) 이 OCR진단_드래그.ahk 아이콘 '위에' 떨어뜨리세요.`n`n"
         . "(더블클릭이 아니라, 끌어다 놓기입니다)", "OCR 진단 - 사용법", 64)
    ExitApp()
}

pdf := A_Args[1]
MsgBox("① 받은 파일:`n" pdf, "진단 1/4", 64)

if (!FileExist(pdf)) {
    MsgBox("파일을 찾을 수 없습니다:`n" pdf, "오류", 16)
    ExitApp()
}

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
MsgBox("④ 인식된 단어 수: " wc "개`n`n"
     . "③의 글자 내용을 캡처해서 보내주세요.", "진단 4/4 - 완료", 64)
ExitApp()
