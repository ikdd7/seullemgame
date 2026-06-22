; ============================================================
;  문서접수 OCR 연동 모듈  (AutoHotkey v2)
;  - 스캔/PDF 문서를 골라 Python 추출기(extract_doc.py)를 돌리고
;    결과를 GUI의 비어있는 첫 행에 자동으로 채운다.
;  - 기존 문서접수_GUI.ahk 의 rows / myGui 구조를 그대로 사용.
;
;  연동 방법:
;    1) 문서접수_main.ahk 에  #Include 문서접수_OCR연동.ahk  추가
;    2) 문서접수_GUI.ahk 의 하단 버튼 줄에 아래 한 줄 추가:
;         global btnPdf := myGui.Add("Button","x390 y" . btnY . " w160 h32 -TabStop","📄 PDF 불러오기")
;         btnPdf.OnEvent("Click", OnLoadPDF)
;    (또는 단축키 F9 로도 호출 가능 — 아래 핫키 참고)
; ============================================================

; ── 환경 설정 (자기 PC 경로에 맞게 1회만 수정) ──────────────
global PY_EXE      := "python"                                  ; 파이썬 실행기 (필요시 전체경로)
global PY_SCRIPT   := A_ScriptDir "\..\extract_doc.py"          ; 추출기 위치
global PY_DB       := A_ScriptDir "\..\대상물DB.csv"            ; 대상물 DB

; ── F9: PDF 불러오기 단축키 ─────────────────────────────────
F9::OnLoadPDF()

; ============================================================
;  버튼/단축키 핸들러
; ============================================================
OnLoadPDF(*) {
    global PY_EXE, PY_SCRIPT, PY_DB, statusBar

    pdf := FileSelect(3, , "접수할 스캔/PDF 문서 선택", "PDF 문서 (*.pdf)")
    if (pdf = "")
        return

    if !FileExist(PY_SCRIPT) {
        MsgBox("추출기를 찾을 수 없습니다:`n" PY_SCRIPT, "오류", 16)
        return
    }

    SetStatus("📄 문서 분석 중… (스캔이면 수 초 소요)")

    ini := A_Temp "\docintake_" A_TickCount ".ini"
    cmd := Format('"{1}" "{2}" "{3}" --db "{4}" --ini "{5}"',
                  PY_EXE, PY_SCRIPT, pdf, PY_DB, ini)

    ; 콘솔창 숨기고 끝날 때까지 대기
    rc := RunWait(A_ComSpec ' /c ' cmd, , "Hide")

    if !FileExist(ini) {
        MsgBox("추출에 실패했습니다.`n파이썬/모듈 설치 상태를 확인하세요.`n`n명령:`n" cmd, "오류", 16)
        SetStatus("❌ 추출 실패")
        return
    }

    d := ReadIni(ini)
    try FileDelete(ini)

    ; ── 확인 후 행에 채우기 ──
    msg := "▶ 문서종류 : " d["doc_type"] "`n"
         . "▶ 대상물명 : " d["building"] "`n"
         . "▶ 주소     : " d["addr"] "`n"
         . "▶ 관계인   : " d["name"] "  (" d["phone"] ")`n"
         . "▶ 점검종류 : " d["status"] "`n"
         . "▶ 부서     : " d["dept"] "`n"
         . "▶ 추출방식 : " d["source"] "   DB매칭: " d["matched"] "`n`n"
         . "이 내용으로 빈 행에 입력할까요?"
    if (MsgBox(msg, "문서 추출 결과 확인", 4 + 32) = "No") {
        SetStatus("취소됨")
        return
    }

    FillRow(d)
}

; ============================================================
;  비어있는 첫 행을 찾아 값 채우기 (없으면 행 추가)
; ============================================================
FillRow(d) {
    global rows, statusBar

    target := 0
    for i, row in rows {
        if (Trim(row.name.Value) = "" && Trim(row.building.Value) = ""
            && Trim(row.addr.Value) = "") {
            target := i
            break
        }
    }
    if (target = 0) {              ; 빈 행 없으면 새 행 추가
        AddRowClick(0)
        target := rows.Length
    }

    row := rows[target]
    row.name.Value     := d["name"]
    row.building.Value := d["building"]
    row.addr.Value     := d["addr"]

    ; 부서 DDL 선택
    SetDeptDDL(row.dep, d["dept"])

    ; 작동/종합 라디오
    if (d["status"] = "종합") {
        row.jong.Value := 1
    } else {
        row.jak.Value := 1
    }

    SetStatus(Format("  {1}행 입력 완료 — {2} ({3})", target, d["building"], d["status"]))
}

; ── 부서명을 DDL 항목과 매칭해 선택 ─────────────────────────
SetDeptDDL(ddl, deptText) {
    if (deptText = "")
        return
    key := InStr(deptText, "중부") ? "중부"
         : InStr(deptText, "미추홀") ? "미추홀" : ""
    if (key = "")
        return
    for idx, item in ControlGetItems(ddl) {
        if InStr(item, key) {
            ddl.Value := idx
            return
        }
    }
}

; ============================================================
;  유틸: BOM 포함 UTF-8 INI 읽기 → Map
; ============================================================
ReadIni(path) {
    m := Map("doc_type","", "building","", "addr","", "name","",
             "phone","", "status","", "dept","", "source","", "matched","")
    txt := FileRead(path, "UTF-8")
    for line in StrSplit(txt, "`n", "`r") {
        if (line = "" || SubStr(line, 1, 1) = "[")
            continue
        p := InStr(line, "=")
        if (p) {
            k := Trim(SubStr(line, 1, p - 1))
            v := Trim(SubStr(line, p + 1))
            m[k] := v
        }
    }
    return m
}

SetStatus(s) {
    global statusBar
    try statusBar.SetText(s)
}
