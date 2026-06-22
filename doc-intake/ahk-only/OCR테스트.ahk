; ============================================================
;  OCR 테스트 (단독 실행)
;  - GUI에 붙이기 전, 스캔/PDF가 제대로 읽히는지 먼저 확인하는 용도.
;  - 더블클릭으로 실행 → PDF 고르면 추출 결과를 보여준다.
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force
#Include 문서추출엔진.ahk

pdf := FileSelect(3, , "OCR 테스트할 스캔/PDF 문서 선택", "PDF 문서 (*.pdf)")
if (pdf = "")
    ExitApp()

try {
    t0 := A_TickCount
    d := ExtractFromPDF(pdf, A_ScriptDir "\대상물DB.csv")
    sec := Round((A_TickCount - t0) / 1000, 1)
} catch as e {
    MsgBox(e.Message, "오류", 16)
    ExitApp()
}

msg := "▶ 문서종류 : " d["doc_type"] "`n"
     . "▶ 대상물명 : " d["building"] "`n"
     . "▶ 주소     : " d["addr"] "`n"
     . "▶ 관계인   : " d["name"] "   (" d["phone"] ")`n"
     . "▶ 점검종류 : " d["status"] "`n"
     . "▶ 부서     : " d["dept"] "`n"
     . "▶ DB매칭   : " d["matched"] "`n`n"
     . "(소요 " sec "초)"
MsgBox(msg, "추출 결과", 64)
ExitApp()
