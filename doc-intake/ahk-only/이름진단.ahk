; ============================================================
;  이름(관계인) 진단 — OCR이 '성명/관계인'을 어떻게 읽었는지 본다.
;  스캔 폴더의 최신 PDF를 OCR해서 전체 텍스트를 메모장에 띄우고,
;  '성명/관계인/성' 들어간 줄을 따로 보여준다.
;  OCR.ahk 와 같은 폴더에 두고 더블클릭.
;  ※ 보고 싶은 문서를 스캔 폴더에서 '제일 최근'이 되게 해두세요(다시 저장 등).
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
    res := OCR.FromPDF(pdf, {lang: "ko", scale: 2})[1]
catch as e {
    MsgBox("OCR 오류: " e.Message, "오류", 16)
    ExitApp()
}

full := res.Text
SplitPath(pdf, &fname)

; '성명/관계인/성' 들어간 줄만 추림
hit := ""
for line in res.Lines {
    t := line.Text
    if (InStr(t, "성명") || InStr(t, "관계인") || InStr(t, "성") || InStr(t, "점검자"))
        hit .= t "`n"
}

; 전체 텍스트는 파일로 저장 + 메모장
txt := A_ScriptDir "\OCR전체텍스트.txt"
try FileDelete(txt)
FileAppend("[" fname "]`n`n=== 이름 관련 줄 ===`n" hit "`n`n=== 전체 ===`n" full, txt, "UTF-8")
try Run('notepad.exe "' txt '"')

MsgBox("[" fname "]`n`n=== 이름 관련 줄 ===`n" (hit = "" ? "(없음)" : hit)
     . "`n위 '이름 관련 줄' 부분을 캡처해서 보내주세요.`n(전체 텍스트는 OCR전체텍스트.txt 에도 저장됨)",
       "이름 진단", 64)
ExitApp()
