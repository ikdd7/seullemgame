; ============================================================
;  OCR 언어 확인 (1초 점검용)
;  - 이 PC에서 한국어 OCR이 되는지 바로 확인한다.
;  - OCR.ahk 와 같은 폴더에 두고 더블클릭.
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force
#Include OCR.ahk

langs := OCR.GetAvailableLanguages()

if (InStr(langs, "ko"))
    MsgBox("✅ 한국어 OCR 사용 가능합니다!`n`n그대로 OCR테스트.ahk 를 실행하면 됩니다.`n`n[설치된 OCR 언어 목록]`n" langs,
           "OCR 언어 확인", 64)
else
    MsgBox("❌ 한국어 OCR이 목록에 없습니다.`n`n"
         . "이 메시지를 그대로 캡처해서 보내주세요. 다른 방법으로 안내해 드릴게요.`n`n"
         . "[설치된 OCR 언어 목록]`n" (langs = "" ? "(없음)" : langs),
           "OCR 언어 확인", 48)
ExitApp()
