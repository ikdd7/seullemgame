; ============================================================
;  OCR 최종 테스트 (폴더 방식) — 파일선택 안 씀
;  스캔 폴더의 '최신 PDF'를 읽어 최종 추출 필드(+DB 보정)를 보여준다.
;  GUI 연동 전, 결과가 제대로 나오는지 확인하는 용도.
;
;  사용: OCR.ahk·문서추출엔진.ahk·대상물DB.csv 와 같은 폴더에 두고 더블클릭.
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force
#Include 문서추출엔진.ahk

global SCAN_FOLDER := "C:\Users\User\Desktop\scan"     ; ← 스캔 폴더 (연동파일과 동일하게)

if !DirExist(SCAN_FOLDER) {
    MsgBox("스캔 폴더를 찾을 수 없습니다:`n" SCAN_FOLDER, "오류", 16)
    ExitApp()
}

pdf := "", newest := 0
Loop Files, SCAN_FOLDER "\*.pdf" {
    if (A_LoopFileTimeModified > newest)
        newest := A_LoopFileTimeModified, pdf := A_LoopFileFullPath
}
if (pdf = "") {
    MsgBox("스캔 폴더에 PDF가 없습니다:`n" SCAN_FOLDER, "PDF 없음", 48)
    ExitApp()
}

SplitPath(pdf, &fname)
try {
    t0 := A_TickCount
    d := ExtractFromPDF(pdf, A_ScriptDir "\대상물DB.csv")
    sec := Round((A_TickCount - t0) / 1000, 1)
} catch as e {
    MsgBox(e.Message, "오류", 16)
    ExitApp()
}

msg := "📄 최신 스캔: " fname "  (소요 " sec "초)`n"
     . "───────────────────────────`n"
     . "▶ 문서종류 : " d["doc_type"] "`n"
     . "▶ 대상물명 : " d["building"] "`n"
     . "▶ 주소     : " d["addr"] "`n"
     . "▶ 관계인   : " d["name"] "   (" d["phone"] ")`n"
     . "▶ 점검종류 : " d["status"] "`n"
     . "▶ 부서     : " d["dept"] "`n"
     . "▶ DB매칭   : " d["matched"]
MsgBox(msg, "추출 결과", 64)
ExitApp()
