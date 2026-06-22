; ============================================================
;  문서접수 OCR 연동 (AutoHotkey 전용 - Python 불필요)
;  기존 문서접수_GUI.ahk 의 rows / myGui / statusBar 구조를 사용.
;
;  연동 방법:
;    1) 이 폴더의 OCR.ahk · 문서추출엔진.ahk · 대상물DB.csv 를
;       매크로 폴더(문서접수_main.ahk 가 있는 곳)에 함께 둔다.
;    2) 문서접수_main.ahk 에 한 줄 추가:
;         #Include 문서접수_OCR연동.ahk
;    3) (선택) 문서접수_GUI.ahk 하단 버튼 줄에 추가:
;         global btnPdf := myGui.Add("Button","x390 y" . btnY . " w160 h32 -TabStop","📄 PDF 불러오기")
;         btnPdf.OnEvent("Click", OnLoadPDF)
;    버튼 없이도 단축키 [F9] 로 바로 호출된다.
; ============================================================
#Requires AutoHotkey v2.0
#Include 문서추출엔진.ahk

global DOC_DB := A_ScriptDir "\대상물DB.csv"

; ── F9: PDF 불러오기 ────────────────────────────────────────
F9::OnLoadPDF()

OnLoadPDF(*) {
    global DOC_DB

    pdf := FileSelect(3, , "접수할 스캔/PDF 문서 선택", "PDF 문서 (*.pdf)")
    if (pdf = "")
        return

    SetStatus("📄 문서 분석 중… (스캔이면 수 초 소요)")
    try {
        d := ExtractFromPDF(pdf, DOC_DB)
    } catch as e {
        MsgBox(e.Message, "오류", 16)
        SetStatus("❌ 추출 실패")
        return
    }

    msg := "▶ 문서종류 : " d["doc_type"] "`n"
         . "▶ 대상물명 : " d["building"] "`n"
         . "▶ 주소     : " d["addr"] "`n"
         . "▶ 관계인   : " d["name"] "   (" d["phone"] ")`n"
         . "▶ 점검종류 : " d["status"] "`n"
         . "▶ 부서     : " d["dept"] "`n"
         . "▶ DB매칭   : " d["matched"] "`n`n"
         . "이 내용으로 빈 행에 입력할까요?"
    if (MsgBox(msg, "문서 추출 결과 확인", 4 + 32) = "No") {
        SetStatus("취소됨")
        return
    }
    FillRow(d)
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
