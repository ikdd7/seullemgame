; ============================================================
;  OCR 진단 (어디서 멈추는지 단계별로 확인)
;  - OCR.ahk 와 같은 폴더에 두고 더블클릭.
;  - 각 단계마다 창이 뜬다. 어느 창까지 떴는지 알려주면 원인을 잡는다.
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force
#Include OCR.ahk

MsgBox("① 시작됨. 다음 창에서 PDF를 고르세요.", "진단 1/5", 64)

pdf := FileSelect(3, , "진단할 스캔/PDF 선택", "PDF 문서 (*.pdf)")
if (pdf = "") {
    MsgBox("파일을 안 골랐습니다(취소). 다시 실행해 PDF를 선택하세요.", "진단 중단", 48)
    ExitApp()
}
MsgBox("② 선택한 파일:`n" pdf, "진단 2/5", 64)

; ── OCR 실행 ──
try {
    t0 := A_TickCount
    results := OCR.FromPDF(pdf, {lang: "ko"})
    sec := Round((A_TickCount - t0) / 1000, 1)
} catch as e {
    MsgBox("❌ OCR 실행 중 오류 발생:`n`n"
         . "메시지: " e.Message "`n"
         . "위치: " e.What "`n"
         . "추가: " (e.HasProp("Extra") ? e.Extra : "") "`n`n"
         . "이 창을 그대로 캡처해서 보내주세요.", "진단 - 오류", 16)
    ExitApp()
}

if (!IsObject(results) || results.Length = 0) {
    MsgBox("❌ OCR 결과가 비어 있습니다(페이지 0).", "진단 - 빈 결과", 48)
    ExitApp()
}
MsgBox("③ OCR 완료. 페이지 수: " results.Length "  (소요 " sec "초)", "진단 3/5", 64)

; ── 원본 인식 텍스트 일부 ──
res := results[1]
raw := res.Text
MsgBox("④ 1페이지에서 읽은 글자(앞부분):`n`n"
     . (raw = "" ? "(아무 글자도 못 읽음!)" : SubStr(raw, 1, 600)),
       "진단 4/5 - 원본 OCR", 64)

; ── 단어 개수 ──
wc := 0
for line in res.Lines
    for w in line.Words
        wc++
MsgBox("⑤ 인식된 단어 수: " wc "개`n`n"
     . "여기까지 떴으면 OCR은 정상입니다.`n"
     . "이 창들 내용(특히 ④의 글자)을 캡처해서 보내주세요.", "진단 5/5", 64)
ExitApp()
