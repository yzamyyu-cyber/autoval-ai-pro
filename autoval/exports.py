"""Professional financial exports (formula-driven Excel workbook + PDF research report).

The Excel workbook is a functioning model: editable assumption cells (blue) drive linked
Excel formulas (black) across the forecast; the DCF/ratios reference those cells. Negative
mechanical equity is retained in audit cells but the headline is suppressed. Deterministic
(no LLM); PDF reuses only matching cached material; no synthetic price presented as genuine.
"""
from __future__ import annotations


def _usd(v):
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "n/a"


def _pct(v):
    return f"{v:.1%}" if isinstance(v, (int, float)) else "n/a"


def build_excel_workbook(result: dict, path: str) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.formatting.rule import ColorScaleRule

    a = result["analysis"]; cases = a["scenarios"]; base = cases["base"]
    drivers = ((a.get("forecast") or {}).get("base") or {}).get("drivers") or {}
    hist = result.get("forecast_history") or {}
    fy = hist.get("fiscal_years") or []
    q = (result.get("quality") or {}).get("state")
    ms = a.get("multistage") or {}

    wb = Workbook()
    NAVY = "1F3864"
    hdr_fill = PatternFill("solid", fgColor=NAVY)
    hdr_font = Font(bold=True, color="FFFFFF")
    blue = Font(color="0000FF")
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def style_header(ws):
        for c in ws[1]:
            c.fill = hdr_fill; c.font = hdr_font; c.alignment = Alignment(horizontal="center")

    # ---- Assumptions (editable, blue) ----
    wa = wb.active; wa.title = "Assumptions"
    wa["A1"] = "Forecast & valuation assumptions — edit blue cells"; wa["A1"].font = Font(bold=True, size=12)
    # Use the SELECTED basis (annual or TTM) base revenue/NWC, not the hardcoded annual value.
    fc_base = (a.get("forecast") or {}).get("base") or {}
    base_rev = fc_base.get("base_revenue") if fc_base.get("base_revenue") is not None else (hist.get("revenue") or [0.0])[-1]
    opening_nwc = fc_base.get("base_nwc") if fc_base.get("base_nwc") is not None else (
        next((v for v in reversed(hist.get("nwc") or []) if v is not None), 0.0))
    roic = (ms.get("assumptions") or {}).get("mature_incremental_roic", 0.12)
    assumptions = [
        ("Base revenue (selected basis)", base_rev, '#,##0'),
        ("Revenue growth", drivers.get("revenue_growth", 0.0), '0.0%'),
        ("Operating margin", drivers.get("operating_margin", 0.0), '0.0%'),
        ("Normalized tax rate", drivers.get("normalized_tax_rate", 0.21), '0.0%'),
        ("D&A / revenue", drivers.get("da_ratio", 0.0), '0.0%'),
        ("CapEx / revenue", drivers.get("capex_ratio", 0.0), '0.0%'),
        ("NWC / revenue", drivers.get("nwc_ratio", 0.0), '0.0%'),
        ("Opening operating NWC", opening_nwc, '#,##0'),
        ("WACC (linked)", "=WACC!E6", '0.0%'),
        ("Terminal growth", base.get("terminal_growth", 0.02), '0.0%'),
        ("Net debt", base.get("net_debt_usd", 0.0), '#,##0'),
        ("Shares (diluted)", a.get("diluted_shares") or a.get("shares_outstanding", 0.0), '#,##0'),
        ("Mature incremental ROIC", roic, '0.0%'),
        ("Transition years (snapshot)", (ms.get("assumptions") or {}).get("transition_years", 5), '0'),
    ]
    for i, (label, val, fmt) in enumerate(assumptions, start=3):
        wa.cell(i, 1, label)
        c = wa.cell(i, 2, val); c.number_format = fmt
        if label.startswith("Transition years"):
            c.font = Font(color="808080")  # display-only (not editable)
        else:
            c.font = blue if not (isinstance(val, str) and val.startswith("=")) else Font(color="000000")
        c.border = border
    wa.column_dimensions["A"].width = 30; wa.column_dimensions["B"].width = 14
    wa.freeze_panes = "A3"

    # ---- FCFF forecast (fully linked; FCFF = NOPAT + D&A − CapEx − ΔNWC) ----
    wf = wb.create_sheet("FCFF Forecast")
    wf.append(["Year", "Revenue", "EBIT", "NOPAT", "D&A", "CapEx", "NWC", "ΔNWC", "FCFF"]); style_header(wf)
    for y in range(1, 6):
        r = y + 1
        wf.cell(r, 1, y)
        if y == 1:
            wf.cell(r, 2, "=Assumptions!B3*(1+Assumptions!B4)")
            wf.cell(r, 8, "=G2-Assumptions!B10")  # ΔNWC = NWC − opening NWC
        else:
            wf.cell(r, 2, f"=B{r-1}*(1+Assumptions!B4)")
            wf.cell(r, 8, f"=G{r}-G{r-1}")
        wf.cell(r, 3, f"=B{r}*Assumptions!B5")
        wf.cell(r, 4, f"=C{r}*(1-Assumptions!B6)")
        wf.cell(r, 5, f"=B{r}*Assumptions!B7")
        wf.cell(r, 6, f"=B{r}*Assumptions!B8")
        wf.cell(r, 7, f"=B{r}*Assumptions!B9")
        wf.cell(r, 9, f"=D{r}+E{r}-F{r}-H{r}")  # FCFF = NOPAT + D&A − CapEx − ΔNWC
        for col in "BCDEFGHI":
            wf[f"{col}{r}"].number_format = '#,##0'
    for col, w in zip("ABCDEFGHI", (6, 16, 14, 14, 13, 13, 14, 13, 14)):
        wf.column_dimensions[col].width = w
    wf.freeze_panes = "A2"

    # ---- WACC (linked) ----
    wacc_calc = ((result.get("wacc") or {}).get("calculation") or {})
    ww = wb.create_sheet("WACC")
    ww.append(["Input", "Value", "Notes"]); style_header(ww)
    wacc_inputs = [
        ("Risk-free rate", wacc_calc.get("risk_free_rate") or 0.04),
        ("Beta", wacc_calc.get("beta") or 1.0),
        ("Equity risk premium (ERP)", wacc_calc.get("equity_risk_premium") or 0.045),
        ("Pre-tax cost of debt", wacc_calc.get("pre_tax_cost_of_debt") or 0.04),
        ("Marginal tax rate", wacc_calc.get("marginal_tax_rate") or 0.21),
        ("Equity weight", wacc_calc.get("equity_weight") or 0.9),
    ]
    for i, (lbl, val) in enumerate(wacc_inputs, start=2):
        ww.cell(i, 1, lbl)
        c = ww.cell(i, 2, val); c.number_format = '0.0%'; c.font = blue
    ww.cell(2, 4, "Cost of equity"); c = ww.cell(2, 5, "=B2+B3*B4"); c.number_format = '0.0%'
    ww.cell(3, 4, "After-tax cost of debt"); c = ww.cell(3, 5, "=B5*(1-B6)"); c.number_format = '0.0%'
    ww.cell(4, 4, "WACC"); c = ww.cell(4, 5, "=B7*E2+(1-B7)*E3"); c.number_format = '0.0%'; c.font = Font(bold=True)
    ww.cell(5, 4, "WACC override (optional)"); c = ww.cell(5, 5, None); c.number_format = '0.0%'; c.font = blue
    ww.cell(6, 4, "Effective WACC"); c = ww.cell(6, 5, '=IF(ISBLANK(E5),E4,E5)'); c.number_format = '0.0%'; c.font = Font(bold=True)
    for col, w in zip("ABCDE", (28, 12, 4, 26, 14)):
        ww.column_dimensions[col].width = w

    # ---- Five-year DCF (linked) ----
    wd = wb.create_sheet("Five-Year DCF")
    wd["A1"] = "Five-year DCF (linked to FCFF forecast, WACC, terminal growth)"; wd["A1"].font = Font(bold=True)
    for i, lbl in enumerate(["Year 1 FCFF", "Year 2 FCFF", "Year 3 FCFF", "Year 4 FCFF", "Year 5 FCFF"],
                            start=2):
        wd.cell(i, 1, lbl)
        wd.cell(i, 2, f"='FCFF Forecast'!I{i}").number_format = '#,##0'
    wd["A8"] = "Terminal value"
    wd["B8"] = ('=IF(WACC!E6<=Assumptions!B12,0,'
                'B6*(1+Assumptions!B12)/(WACC!E6-Assumptions!B12))')
    wd["B8"].number_format = '#,##0'
    wd["B8"].number_format = '#,##0'
    wd["A9"] = "Terminal value (PV)"
    wd["B9"] = "=B8/(1+WACC!E6)^5"; wd["B9"].number_format = '#,##0'
    wd["A10"] = "Enterprise value"
    wd["B10"] = ("=B2/(1+WACC!E6)+B3/(1+WACC!E6)^2+B4/(1+WACC!E6)^3+B5/(1+WACC!E6)^4"
                 "+B6/(1+WACC!E6)^5+B9"); wd["B10"].number_format = '#,##0'
    wd["A11"] = "Equity value"; wd["B11"] = "=B10-Assumptions!B13"; wd["B11"].number_format = '#,##0'
    wd["A12"] = "Intrinsic/share"
    wd["B12"] = ('=IF(OR(WACC!E6<=Assumptions!B12,Assumptions!B14<=0),"unavailable",'
                 'B11/Assumptions!B14)')
    wd["B12"].number_format = '$#,##0.00'
    wd["A12"].font = Font(bold=True); wd["B12"].font = Font(bold=True)
    headline = base["intrinsic_per_share_usd"] if (q in ("available", "low_confidence")
                                                   and base["intrinsic_per_share_usd"] >= 0) else None
    wd["D1"] = "Snapshot headline"; wd["D1"].fill = hdr_fill; wd["D1"].font = hdr_font
    wd["D2"] = headline if headline is not None else "N/A — Model Review Required"
    wd["E1"] = "Snapshot quality"; wd["E2"] = q
    for col, w in zip("ABCDE", (22, 22, 4, 24, 18)):
        wd.column_dimensions[col].width = w

    # ---- Multi-stage DCF (linked, ROIC-consistent terminal) ----
    wm = wb.create_sheet("Multi-Stage DCF")
    wm["A1"] = "Multi-stage DCF (reproduces Python: explicit 1-5 + transition + ROIC terminal)"
    wm["A1"].font = Font(bold=True)
    # Helpers
    wm["A3"] = "Sustainable reinvestment (g/ROIC)"
    wm["B3"] = "=IF(Assumptions!B15<=0,0,Assumptions!B12/Assumptions!B15)"
    wm["B3"].number_format = '0.0%'
    wm["A4"] = "Explicit reinvestment rate (year 5)"
    wm["B4"] = "=('FCFF Forecast'!F6-'FCFF Forecast'!E6+'FCFF Forecast'!H6)/'FCFF Forecast'!D6"
    wm["B4"].number_format = '0.0%'
    # Transition table (years 6-10), header row 6
    heads = ["Year", "Growth", "Margin", "Reinvestment", "Revenue", "NOPAT", "FCFF"]
    for j, h in enumerate(heads, start=1):
        wm.cell(6, j, h).font = hdr_font; wm.cell(6, j).fill = hdr_fill
    for t in range(5):  # transition years 6..10, t=0..4
        r = 7 + t
        wm.cell(r, 1, 6 + t)
        # growth fade: g_explicit + (tg - g_explicit) * (t+1)/transition
        wm.cell(r, 2, f"=Assumptions!B4+(Assumptions!B12-Assumptions!B4)*({t+1}/5)")
        wm.cell(r, 2).number_format = '0.0%'
        wm.cell(r, 3, "=Assumptions!B5")  # sustainable margin = explicit margin
        wm.cell(r, 3).number_format = '0.0%'
        wm.cell(r, 4, f"=$B$4+($B$3-$B$4)*({t+1}/5)")
        wm.cell(r, 4).number_format = '0.0%'
        if t == 0:
            wm.cell(r, 5, "='FCFF Forecast'!B6*(1+B7)")
        else:
            wm.cell(r, 5, f"=E{r-1}*(1+B{r})")
        wm.cell(r, 5).number_format = '#,##0'
        wm.cell(r, 6, f"=E{r}*C{r}*(1-Assumptions!B6)")
        wm.cell(r, 6).number_format = '#,##0'
        wm.cell(r, 7, f"=F{r}*(1-D{r})")
        wm.cell(r, 7).number_format = '#,##0'
    # Terminal (year 11) + discount
    wm["A13"] = "Terminal FCFF (year 11)"; wm["B13"] = "=E11*(1+Assumptions!B12)*Assumptions!B5*(1-Assumptions!B6)*(1-$B$3)"
    wm["B13"].number_format = '#,##0'
    wm["A14"] = "Terminal value"
    wm["B14"] = ('=IF(OR(WACC!E6<=Assumptions!B12,Assumptions!B15<=0),0,'
                 'B13/(WACC!E6-Assumptions!B12))')
    wm["B14"].number_format = '#,##0'
    wm["A15"] = "PV explicit (1-5)"
    wm["B15"] = ("='FCFF Forecast'!I2/(1+WACC!E6)+'FCFF Forecast'!I3/(1+WACC!E6)^2"
                 "+'FCFF Forecast'!I4/(1+WACC!E6)^3+'FCFF Forecast'!I5/(1+WACC!E6)^4"
                 "+'FCFF Forecast'!I6/(1+WACC!E6)^5"); wm["B15"].number_format = '#,##0'
    wm["A16"] = "PV transition (6-10)"
    wm["B16"] = "=G7/(1+WACC!E6)^6+G8/(1+WACC!E6)^7+G9/(1+WACC!E6)^8+G10/(1+WACC!E6)^9+G11/(1+WACC!E6)^10"
    wm["B16"].number_format = '#,##0'
    wm["A17"] = "Terminal PV"; wm["B17"] = "=B14/(1+WACC!E6)^10"; wm["B17"].number_format = '#,##0'
    wm["A18"] = "Enterprise value"; wm["B18"] = "=B15+B16+B17"; wm["B18"].number_format = '#,##0'
    wm["A19"] = "Equity value"; wm["B19"] = "=B18-Assumptions!B13"; wm["B19"].number_format = '#,##0'
    wm["A20"] = "Multi-stage intrinsic/share"
    wm["B20"] = ('=IF(OR(WACC!E6<=Assumptions!B12,Assumptions!B15<=0,Assumptions!B14<=0),'
                 '"unavailable",B19/Assumptions!B14)')
    wm["B20"].number_format = '$#,##0.00'
    wm["A20"].font = Font(bold=True); wm["B20"].font = Font(bold=True)
    wm.column_dimensions["A"].width = 34; wm.column_dimensions["B"].width = 22

    # ---- Sensitivity (formula-driven matrix) ----
    ws = wb.create_sheet("Sensitivity")
    offsets = (-0.015, -0.010, 0.0, 0.010, 0.015)
    tg_offsets = (-0.005, 0.0, 0.005)  # terminal-growth offsets around the effective assumption
    ws.append(["Intrinsic/share — WACC × terminal growth"] + ["tg"] * len(tg_offsets)); style_header(ws)
    for j, d in enumerate(tg_offsets, start=2):
        ws.cell(1, j, f"=Assumptions!B12+{d}").number_format = '0.0%'  # linked terminal-growth headers
    for i, d in enumerate(offsets, start=2):
        # dynamic WACC row header (formula), centered on effective WACC
        h = ws.cell(i, 1, f"=WACC!E6+{d}")
        h.number_format = '0.0%'; h.font = blue
        for j, _t in enumerate(tg_offsets, start=2):
            col = get_column_letter(j)
            f = ("=IF(OR($A{i}<={col}$1,Assumptions!B14<=0),\"unavailable\","
                 "('FCFF Forecast'!I2/(1+$A{i})+('FCFF Forecast'!I3/(1+$A{i})^2)+"
                 "('FCFF Forecast'!I4/(1+$A{i})^3)+('FCFF Forecast'!I5/(1+$A{i})^4)+"
                 "('FCFF Forecast'!I6/(1+$A{i})^5)+"
                 "('FCFF Forecast'!I6*(1+{col}$1)/($A{i}-{col}$1))/(1+$A{i})^5"
                 "-Assumptions!B13)/Assumptions!B14)").format(i=i, col=col)
            c = ws.cell(i, j, f)
            c.number_format = '$#,##0.00' if c != "unavailable" else 'General'
    rng = f"B2:{get_column_letter(len(tg_offsets)+1)}{len(offsets)+1}"
    ws.conditional_formatting.add(rng, ColorScaleRule(
        start_type="min", start_color="F8696B", end_type="max", end_color="63BE7B"))

    # ---- Historical & ratios (linked margin) ----
    wh = wb.create_sheet("Historical & Ratios")
    wh.append(["Fiscal year", "Revenue", "Operating income", "Margin", "CapEx", "D&A"]); style_header(wh)
    for idx, y in enumerate(fy):
        row = idx + 2
        rev = hist["revenue"][idx]; op = hist["operating_income"][idx]
        wh.cell(row, 1, y[:10])
        wh.cell(row, 2, rev).number_format = '#,##0'
        wh.cell(row, 3, op).number_format = '#,##0'
        wh.cell(row, 4, f"=C{row}/B{row}").number_format = '0.0%'
        wh.cell(row, 5, hist["capex"][idx]).number_format = '#,##0'
        wh.cell(row, 6, hist["da"][idx]).number_format = '#,##0'
    for col, w in zip("ABCDEF", (12, 16, 18, 10, 16, 14)):
        wh.column_dimensions[col].width = w

    # ---- Financial evidence (static, labelled) ----
    we = wb.create_sheet("Financial Evidence")
    we.append(["Evidence ID", "Metric", "Value", "Verification", "Kind"]); style_header(we)
    for e in (result.get("evidence") or [])[:40]:
        v = e.get("reported_value") if e.get("reported_value") is not None else e.get("derived_value")
        we.append([e.get("evidence_id"), e.get("metric"), v, e.get("verification_status"), e.get("kind")])
    we.column_dimensions["A"].width = 30; we.column_dimensions["B"].width = 24

    # ---- Model limitations ----
    wl = wb.create_sheet("Model Limitations")
    wl.append(["Limitation"]); style_header(wl)
    for l in result.get("limitations", []):
        wl.append([l])
    wl.column_dimensions["A"].width = 100

    wb.save(path)
    return path


def build_pdf_report(result: dict, path: str) -> str:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from pathlib import Path

    a = result["analysis"]; cases = a["scenarios"]; base = cases["base"]
    q = (result.get("quality") or {}).get("state")
    ms = a.get("multistage") or {}
    ticker = result.get("ticker", "")
    styles = getSampleStyleSheet()
    NAVY = colors.HexColor("#1F3864"); TEAL = colors.HexColor("#0B7C70")

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#5A6B7B"))
        canvas.drawString(0.75 * inch, 0.5 * inch, f"{result.get('company')} ({ticker}) — Equity Research Report")
        canvas.drawRightString(letter[0] - 0.75 * inch, 0.5 * inch, f"Page {doc_.page}")
        canvas.setStrokeColor(TEAL)
        canvas.line(0.75 * inch, 0.62 * inch, letter[0] - 0.75 * inch, 0.62 * inch)
        canvas.restoreState()

    doc = SimpleDocTemplate(path, pagesize=letter,
                            leftMargin=0.8*inch, rightMargin=0.8*inch,
                            topMargin=0.7*inch, bottomMargin=0.8*inch,
                            title=f"{ticker} Equity Research Report")
    story = []

    def H(t): story.append(Paragraph(t, styles["Heading1"]))
    def H2(t): story.append(Paragraph(t, styles["Heading2"]))
    def P(t): story.append(Paragraph(t, styles["Normal"]))

    # Title block
    story.append(Paragraph(f"{result.get('company')} ({ticker})", styles["Title"]))
    story.append(Paragraph("Equity Research Report", styles["Normal"]))
    P(f"Snapshot {result.get('run_utc')} · Valuation quality <b>{q}</b> · "
      f"Market data <b>{result.get('market_mode')}</b> · WACC basis <b>{result.get('wacc_basis')}</b> · "
      f"Valuation basis {result.get('valuation_basis', 'annual')}")
    story.append(Spacer(1, 10))

    # Executive summary
    H("Executive Summary")
    headline = base["intrinsic_per_share_usd"] if (q in ("available", "low_confidence")
                                                   and base["intrinsic_per_share_usd"] >= 0) else None
    P(f"<b>Headline intrinsic value per share:</b> "
      f"{_usd(headline) if headline is not None else 'N/A — Model Review Required'}")
    if q in ("unavailable", "unsuitable") or headline is None:
        P("The base-case equity residual is negative or material model limitations invalidate "
          "the headline. Signed mechanical values are retained in the audit section below and "
          "are not presented as a meaningful share price.")
    story.append(Spacer(1, 10))

    # Valuation overview
    H("Valuation Overview — Five-year vs Multi-stage DCF")
    rows = [["Scenario", "5-yr DCF/share", "Multi-stage/share", "WACC", "Terminal g"]]
    for c in ("bear", "base", "bull"):
        rows.append([c.title(), _usd(cases[c]["intrinsic_per_share_usd"]),
                     _usd(ms[c]["intrinsic_per_share_usd"]) if c in ms else "—",
                     _pct(cases[c]["wacc"]), _pct(cases[c]["terminal_growth"])])
    t = Table(rows, hAlign="LEFT")
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
    story.append(t); story.append(Spacer(1, 8))

    draw = Drawing(460, 150)
    bc = VerticalBarChart(); bc.x, bc.y, bc.width, bc.height = 55, 30, 370, 100
    bc.data = [[max(cases[c]["intrinsic_per_share_usd"], 0) for c in ("bear", "base", "bull")],
               [max(ms[c]["intrinsic_per_share_usd"], 0) for c in ("bear", "base", "bull") if c in ms]]
    bc.categoryAxis.categoryNames = ["Bear", "Base", "Bull"]
    bc.groupSpacing = 8; bc.barSpacing = 2
    draw.add(bc); story.append(draw); story.append(Spacer(1, 8))
    if any(cases[c]["intrinsic_per_share_usd"] < 0 for c in ("bear", "base", "bull")):
        P("<i>Audit note: negative mechanical values are clipped at zero on the chart; signed "
          "figures appear in the table above.</i>")

    story.append(PageBreak())

    # Historical performance
    hist = result.get("forecast_history") or {}
    fy = hist.get("fiscal_years") or []
    if fy and hist.get("revenue"):
        H("Historical Financial Performance")
        hrows = [["Fiscal year", "Revenue (USD M)", "Op income (USD M)", "Margin", "CapEx (USD M)"]]
        for i, y in enumerate(fy):
            rev = hist["revenue"][i]/1e6; op = hist["operating_income"][i]/1e6
            hrows.append([y[:10], f"{rev:,.0f}", f"{op:,.0f}",
                          f"{op/rev:.1%}" if rev else "—", f"{hist['capex'][i]/1e6:,.0f}"])
        ht = Table(hrows, hAlign="LEFT")
        ht.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                ("BACKGROUND", (0, 0), (-1, 0), TEAL),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
        story.append(ht); story.append(Spacer(1, 8))

        lc = HorizontalLineChart(); lc.x, lc.y, lc.width, lc.height = 45, 30, 390, 110
        lc.data = [[rev/1e6 for rev in hist["revenue"]]]
        lc.categoryAxis.categoryNames = [y[2:4] for y in fy]
        lc.lines[0].strokeColor = TEAL; lc.lines[0].strokeWidth = 2
        d2 = Drawing(450, 150); d2.add(lc)
        story.append(d2); story.append(Spacer(1, 8))

    # Forecast + transition schedule
    fc_rows = ((a.get("forecast") or {}).get("base") or {}).get("rows") or []
    if fc_rows:
        H("Forecast & Transition Schedule")
        fr = [["Year", "Revenue", "NOPAT", "D&A", "CapEx", "FCFF"]]
        for r in fc_rows:
            fr.append([str(r.get("year", "")), f"{r['revenue']/1e6:,.0f}", f"{r['nopat']/1e6:,.0f}",
                       f"{r['da']/1e6:,.0f}", f"{r['capex']/1e6:,.0f}", f"{r['fcff']/1e6:,.0f}"])
        tr = (ms.get("base") or {}).get("transition_rows") or []
        for r in tr:
            fr.append([str(r.get("year", "")), f"{r['revenue']/1e6:,.0f}", f"{r['nopat']/1e6:,.0f}",
                       "—", "—", f"{r['fcff']/1e6:,.0f}"])
        ft = Table(fr, hAlign="LEFT")
        ft.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
        story.append(ft); story.append(Spacer(1, 8))

    # WACC decomposition
    wacc_calc = ((result.get("wacc") or {}).get("calculation") or {})
    if wacc_calc:
        H("WACC Decomposition & Terminal Assumptions")
        wr = [["Input", "Value"], ["Risk-free rate", _pct(wacc_calc.get("risk_free_rate"))],
              ["Beta", f"{wacc_calc.get('beta', 0):.2f}"], ["Equity risk premium", _pct(wacc_calc.get("equity_risk_premium"))],
              ["Cost of equity", _pct(wacc_calc.get("cost_of_equity"))],
              ["After-tax cost of debt", _pct(wacc_calc.get("after_tax_cost_of_debt"))],
              ["Equity weight", _pct(wacc_calc.get("equity_weight"))], ["WACC", _pct(wacc_calc.get("wacc"))]]
        wt = Table(wr, hAlign="LEFT")
        wt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                ("BACKGROUND", (0, 0), (-1, 0), TEAL),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]))
        story.append(wt); story.append(Spacer(1, 6))
        if base.get("terminal_growth") is not None:
            P(f"Terminal growth {_pct(base['terminal_growth'])} · mature incremental ROIC "
              f"{(ms.get('assumptions') or {}).get('mature_incremental_roic', 0.12):.0%} · "
              f"sustainable reinvestment rate {_pct(base['terminal_growth']/((ms.get('assumptions') or {}).get('mature_incremental_roic', 0.12)))}")
        story.append(Spacer(1, 6))

    # Assumptions
    drivers = ((a.get("forecast") or {}).get("base") or {}).get("drivers") or {}
    if drivers:
        H("Forecast Assumptions")
        for k, lbl in (("revenue_growth", "Revenue growth"), ("operating_margin", "Operating margin"),
                       ("normalized_tax_rate", "Tax rate"), ("da_ratio", "D&A / revenue"),
                       ("capex_ratio", "CapEx / revenue"), ("nwc_ratio", "NWC / revenue")):
            if k in drivers:
                P(f"• {lbl}: {_pct(drivers[k])}")
        story.append(Spacer(1, 6))

    story.append(PageBreak())

    # Sensitivity recomputed from the SELECTED forecast (annual or TTM), not a cached matrix.
    fc = (a.get("forecast") or {}).get("base") or {}
    fcff = [r["fcff"] for r in fc.get("rows", [])]
    if fcff:
        from .finance import dcf_from_fcff
        wacc_v = base.get("wacc"); tg_v = base.get("terminal_growth")
        net_debt = base.get("net_debt_usd"); shares = a.get("diluted_shares") or a.get("shares_outstanding")
        waccs = [wacc_v + d for d in (-0.015, -0.010, 0.0, 0.010, 0.015)]
        tgs = [tg_v + d for d in (-0.005, 0.0, 0.005)]
        H("Valuation Sensitivity (WACC × terminal growth → intrinsic/share)")
        sr = [["WACC \\ Term g"] + [f"{t:.1%}" for t in tgs]]
        for w in waccs:
            row = [f"{w:.2%}"]
            for t in tgs:
                if w <= t or shares is None or shares <= 0:
                    row.append("—")
                else:
                    row.append(_usd(dcf_from_fcff(fcff, shares, net_debt, w, t)["intrinsic_per_share_usd"]))
            sr.append(row)
        st_ = Table(sr, hAlign="LEFT")
        st_.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                 ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]))
        story.append(st_); story.append(Spacer(1, 8))

    # Industry & peers
    rel = result.get("relative")
    if rel:
        H("Industry & Comparable Companies")
        for gkey, g in rel.get("groups", {}).items():
            pe = g.get("pe", {}); ev = g.get("ev_ebitda", {})
            pe_med = pe.get("median_pe"); ev_med = ev.get("median_ev_ebitda")
            pe_txt = f"{pe_med:.1f}x" if pe_med else "—"
            ev_txt = f"{ev_med:.1f}x" if ev_med else "—"
            P(f"• {gkey.replace('_', ' ').title()} ({g.get('sample_size', 0)} peers): "
              f"P/E median {pe_txt} → implied {_usd(pe.get('implied_price_median'))}; "
              f"EV/EBITDA median {ev_txt} → implied {_usd(ev.get('implied_price_median'))}")
        story.append(Spacer(1, 8))
    else:
        H("Industry & Comparable Companies")
        P("Peer multiples are unavailable for this snapshot (fixture or no live peer retrieval).")

    # Cached AI narrative (only when it matches this snapshot's company)
    _append_cached_narrative(story, ticker, styles)
    _append_reconciliation_findings(story, ticker, result, styles)

    # Risks & limitations
    H("Risks, Model Limitations & SEC Sources")
    for l in result.get("limitations", [])[:14]:
        P(f"• {l}")
    fin = (result.get("provenance") or {}).get("financials") or {}
    if fin.get("url"):
        P(f"<br/>SEC company facts: <font size=8>{fin['url']}</font>")

    doc.build(story, onLaterPages=footer, onFirstPage=footer)
    return path


def _append_cached_narrative(story, ticker, styles):
    from reportlab.platypus import Paragraph
    from pathlib import Path
    cands = [f"research_report_{t}.md" for t in (ticker.lower(),)] + ["research_report_msft.md"]
    root = Path(__file__).resolve().parent.parent
    path = None
    for c in cands:
        p = root / "evidence" / c
        if p.exists():
            path = p; break
    if not path:
        return
    text = path.read_text(encoding="utf-8")
    # extract the conclusion section (matching company only)
    m = None
    for sec in ("## Research conclusion", "## Evidence-backed research conclusion"):
        i = text.find(sec)
        if i >= 0:
            m = text[i:i+1400]
            break
    if m and ticker.lower() in path.name:
        story.append(Paragraph("AI Research Analyst — Historical Case Study (not re-matched to this snapshot)",
                               styles["Heading2"]))
        story.append(Paragraph(m.split("\n", 1)[-1][:1400].replace("\n", "<br/>"), styles["Normal"]))


def _append_reconciliation_findings(story, ticker, result, styles):
    from reportlab.platypus import Paragraph
    from pathlib import Path
    import json as _json
    root = Path(__file__).resolve().parent.parent
    rec_dir = root / "evidence" / "reconciliation_records"
    if not rec_dir.is_dir():
        return
    files = sorted(rec_dir.glob(f"{ticker}_*.json"))
    if not files:
        return
    try:
        d = _json.load(open(files[-1], encoding="utf-8"))
    except Exception:
        return
    v = (d.get("deterministic_validation") or {}).get("status")
    if d.get("proposed_financial_value") is None and not d.get("detected_problem"):
        return
    story.append(Paragraph("AI Financial Reconciliation — Findings", styles["Heading2"]))
    story.append(Paragraph(f"• Issue: {d.get('detected_problem')}", styles["Normal"]))
    if d.get("proposed_financial_value") is not None:
        story.append(Paragraph(f"• Proposed correction: {_usd(d.get('proposed_financial_value'))} "
                               f"(original {_usd(d.get('original_production_value'))}) · "
                               f"validation {v}", styles["Normal"]))