; ============================================================
;  문서접수 OCR 연동 (AutoHotkey 전용 - Python 불필요)
;  ★ 파일 선택 창 없이, 스캔 폴더의 '최신 PDF'를 자동으로 읽어 입력 ★
;  기존 문서접수_GUI.ahk 의 rows / myGui / statusBar 구조를 사용.
;
;  연동 방법:
;    1) OCR.ahk · 문서추출엔진.ahk · 대상물DB.csv · 이 파일을
;       매크로 폴더(문서접수_main.ahk 가 있는 곳)에 함께 둔다.
;    2) 문서접수_main.ahk 에 한 줄 추가:
;         #Include 문서접수_OCR연동.ahk
;    3) (선택) 문서접수_GUI.ahk 하단 버튼 줄에 추가:
;         global btnPdf := myGui.Add("Button","x390 y" . btnY . " w160 h32 -TabStop","📄 스캔 불러오기")
;         btnPdf.OnEvent("Click", OnLoadPDF)
;    버튼 없이도 단축키 [F9] 로 호출된다.
;
;  사용:  문서를 스캔(→ 스캔 폴더에 PDF 저장) → [F9] → 확인창 → 빈 행 자동입력
; ============================================================
#Requires AutoHotkey v2.0
#Include 문서추출엔진.ahk

; ── 환경 설정 (필요시 수정) ─────────────────────────────────
global SCAN_FOLDER := "C:\Users\User\Desktop\scan"     ; 스캔 PDF가 저장되는 폴더
global DOC_DB      := A_ScriptDir "\대상물DB.csv"        ; 대상물 DB

; ── F9: 스캔 폴더의 최신 PDF 불러오기 ───────────────────────
F9::OnLoadPDF()

OnLoadPDF(*) {
    global SCAN_FOLDER, DOC_DB

    if !DirExist(SCAN_FOLDER) {
        MsgBox("스캔 폴더를 찾을 수 없습니다:`n" SCAN_FOLDER
             . "`n`n문서접수_OCR연동.ahk 상단의 SCAN_FOLDER 경로를 확인하세요.", "오류", 16)
        return
    }

    pdf := NewestPDF(SCAN_FOLDER, &mtime)
    if (pdf = "") {
        MsgBox("스캔 폴더에 PDF가 없습니다:`n" SCAN_FOLDER, "PDF 없음", 48)
        return
    }

    SplitPath(pdf, &fname)
    SetStatus("📄 분석 중… " fname)

    try {
        d := ExtractFromPDF(pdf, DOC_DB)
    } catch as e {
        MsgBox(e.Message, "오류", 16)
        SetStatus("❌ 추출 실패")
        return
    }

    msg := "📄 최신 스캔: " fname "`n"
         . "    (저장시각 " FormatTime(mtime, "MM/dd HH:mm") ")`n"
         . "───────────────────────────`n"
         . "▶ 문서종류 : " d["doc_type"] "`n"
         . "▶ 대상물명 : " d["building"] "`n"
         . "▶ 주소     : " d["addr"] "`n"
         . "▶ 관계인   : " d["name"] "   (" d["phone"] ")`n"
         . "▶ 점검종류 : " d["status"] "`n"
         . "▶ 부서     : " d["dept"] "`n"
         . "▶ DB매칭   : " d["matched"] "`n"
         . "───────────────────────────`n"
         . "새 파일명 : " MakeFileName(d) "`n"
         . "───────────────────────────`n"
         . "이 내용으로 빈 행에 입력하고, 파일명도 변경할까요?"
    if (MsgBox(msg, "문서 추출 결과 확인", 4 + 32) = "No") {
        SetStatus("취소됨")
        return
    }
    FillRow(d)
    RenamePDF(pdf, d)
}

; ── 문서종류+대상물명으로 표준 파일명 만들기 ────────────────
MakeFileName(d) {
    static DOC_NAME := Map("이행완료보고서", "이행완료 보고서",
                           "이행계획서",     "이행계획서",
                           "결과보고서",     "자체점검 결과보고서",
                           "미상",           "문서")
    docName := DOC_NAME.Has(d["doc_type"]) ? DOC_NAME[d["doc_type"]] : d["doc_type"]
    base := (d["building"] != "") ? docName "(" d["building"] ")" : docName
    return CleanFileName(base) ".pdf"
}

; ── 파일명 자동변경 (덮어쓰기 방지, 중복 시 (2)…) ───────────
RenamePDF(pdf, d) {
    SplitPath(pdf, &oldName, &dir)
    newName := MakeFileName(d)
    if (newName = oldName)
        return
    target := dir "\" newName
    if FileExist(target) {                 ; 동명 존재 → (2),(3)… 붙임
        SplitPath(newName, , , , &stem)
        n := 2
        while FileExist(dir "\" stem "(" n ").pdf")
            n++
        target := dir "\" stem "(" n ").pdf"
    }
    try {
        FileMove(pdf, target)
        SplitPath(target, &tn)
        SetStatus("📄 파일명 변경: " tn)
    } catch as e {
        MsgBox("파일명 변경 실패(파일이 열려있을 수 있음):`n" e.Message, "알림", 48)
    }
}

; 파일명에 못 쓰는 문자 제거
CleanFileName(s) => RegExReplace(s, '[\\/:*?"<>|]', "")

; ── 폴더에서 가장 최근 PDF 찾기 ─────────────────────────────
NewestPDF(folder, &mtime) {
    pdf := "", newest := 0
    Loop Files, folder "\*.pdf" {
        if (A_LoopFileTimeModified > newest)
            newest := A_LoopFileTimeModified, pdf := A_LoopFileFullPath
    }
    mtime := newest
    return pdf
}

; ── 비어있는 첫 행을 찾아 채우기 (없으면 행 추가) ───────────
FillRow(d) {
    global rows

    target := 0
    for i, row in rows {
        if (Trim(row.name.Value) = "" && Trim(row.building.Value) = ""
            && Trim(row.addr.Value) = "") {
            target := i
            break
        }
    }
    if (target = 0) {
        AddRowClick(0)               ; 문서접수_GUI.ahk 의 행 추가 핸들러
        target := rows.Length
    }

    row := rows[target]
    row.name.Value     := d["name"]
    row.building.Value := d["building"]
    row.addr.Value     := d["addr"]
    SetDeptDDL(row.dep, d["dept"])
    if (d["status"] = "종합")
        row.jong.Value := 1
    else
        row.jak.Value := 1

    SetStatus(target "행 입력 완료 — " d["building"] " (" d["status"] ")")
}

; ── 부서명을 DDL 항목과 매칭해 선택 ─────────────────────────
SetDeptDDL(ddl, deptText) {
    if (deptText = "")
        return
    key := InStr(deptText, "중부") ? "중부"
         : InStr(deptText, "미추홀") ? "미추홀" : ""
    if (key = "")
        return
    for idx, item in ControlGetItems(ddl)
        if InStr(item, key) {
            ddl.Value := idx
            return
        }
}

SetStatus(s) {
    global statusBar
    try statusBar.SetText("  " s)
}
