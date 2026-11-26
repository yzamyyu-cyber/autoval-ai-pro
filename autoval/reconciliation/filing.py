"""Original-filing (Inline XBRL) evidence retrieval.

When standard companyfacts extraction fails or a tag is missing/stale, this module reads
the original 10-K/10-Q HTML and extracts the inline XBRL facts (with their reporting
contexts, units, scale and sign), plus the rendered financial-statement table rows and the
note text. All retrieved content is untrusted data to inspect — never executed.
"""
from __future__ import annotations
import re
from urllib.request import Request, urlopen


def fetch_filing(url: str, user_agent: str) -> str:
    req = Request(url, headers={"User-Agent": user_agent})
    return urlopen(req, timeout=60).read().decode("utf-8", "ignore")


def extract_contexts(html: str) -> dict:
    """Map context id -> {instant|start|end} from xbrli:context elements."""
    out: dict = {}
    for m in re.finditer(r"<xbrli:context[^>]*id=\"([^\"]+)\"[^>]*>(.*?)</xbrli:context>",
                         html, re.DOTALL | re.IGNORECASE):
        cid, body = m.group(1), m.group(2)
        ctx: dict = {}
        inst = re.search(r"<xbrli:instant[^>]*>([^<]+)</xbrli:instant>", body, re.IGNORECASE)
        start = re.search(r"<xbrli:startDate[^>]*>([^<]+)</xbrli:startDate>", body, re.IGNORECASE)
        end = re.search(r"<xbrli:endDate[^>]*>([^<]+)</xbrli:endDate>", body, re.IGNORECASE)
        if inst:
            ctx["instant"] = inst.group(1).strip()
        if start:
            ctx["start"] = start.group(1).strip()
        if end:
            ctx["end"] = end.group(1).strip()
        out[cid] = ctx
    return out


def extract_units(html: str) -> dict:
    """Map unit id -> unit name (e.g. 'usd', 'shares')."""
    out: dict = {}
    for m in re.finditer(r"<xbrli:unit[^>]*id=\"([^\"]+)\"[^>]*>(.*?)</xbrli:unit>",
                         html, re.DOTALL | re.IGNORECASE):
        body = m.group(2)
        measure = re.search(r"<xbrli:measure[^>]*>([^<]+)</xbrli:measure>", body, re.IGNORECASE)
        if measure:
            out[m.group(1)] = measure.group(1).strip().split(":")[-1]
    return out


def _parse_inline(text: str) -> dict:
    text = text.strip()
    return float(text.replace(",", "").replace("\u2212", "-").replace("(", "-").replace(")", ""))


def extract_inline_facts(html: str) -> list[dict]:
    """Extract every ix:nonFraction / ix:nonNumeric fact with its attributes."""
    facts: list[dict] = []
    for kind in ("nonFraction", "nonNumeric"):
        for m in re.finditer(
                rf"<ix:{kind}\b([^>]*)>(.*?)</ix:{kind}>", html, re.DOTALL | re.IGNORECASE):
            attrs = m.group(1)
            inner = m.group(2)
            name = re.search(r"name=\"([^\"]+)\"", attrs)
            ctx = re.search(r"contextRef=\"([^\"]+)\"", attrs)
            unit = re.search(r"unitRef=\"([^\"]+)\"", attrs)
            scale = re.search(r"scale=\"([^\"]+)\"", attrs)
            sign = re.search(r"sign=\"([^\"]+)\"", attrs)
            decimals = re.search(r"decimals=\"([^\"]+)\"", attrs)
            # value is the inner text (or the value attribute for nonNumeric)
            raw = re.sub(r"<[^>]+>", "", inner).strip()
            value = re.search(r"value=\"([^\"]+)\"", attrs)
            sign_val = sign.group(1) if sign else None
            sign_num = -1 if sign_val == "-" else (int(sign_val) if sign_val not in (None, "+") else 1)
            facts.append({
                "name": name.group(1) if name else None,
                "tag": (name.group(1).split(":")[-1] if name else None),
                "context_ref": ctx.group(1) if ctx else None,
                "unit": unit.group(1) if unit else None,
                "scale": int(scale.group(1)) if scale else 0,
                "sign": sign_num,
                "decimals": decimals.group(1) if decimals else None,
                "raw_value": raw if raw else (value.group(1) if value else None),
                "kind": kind,
            })
    return facts


def resolve_fact(fact: dict, contexts: dict, units: dict) -> dict:
    """Resolve an inline fact to {value, unit, period_end, period_start}."""
    ctx = contexts.get(fact.get("context_ref") or "", {})
    unit_id = fact.get("unit") or ""
    unit = units.get(unit_id, unit_id)
    value = None
    raw = fact.get("raw_value")
    if raw is not None and fact.get("kind") == "nonFraction":
        try:
            value = _parse_inline(str(raw)) * (10 ** fact.get("scale", 0)) * fact.get("sign", 1)
        except ValueError:
            value = None
    return {"tag": fact.get("tag"), "name": fact.get("name"),
            "value": value, "raw_value": raw, "unit": unit,
            "period_end": ctx.get("instant") or ctx.get("end"),
            "period_start": ctx.get("start"),
            "scale": fact.get("scale"), "sign": fact.get("sign"),
            "decimals": fact.get("decimals")}


def lookup_fact(html: str, tag: str, period: str | None = None) -> dict | None:
    """Find an inline fact by us-gaap tag, optionally at a specific period_end."""
    contexts = extract_contexts(html)
    units = extract_units(html)
    facts = [resolve_fact(f, contexts, units) for f in extract_inline_facts(html)
             if f.get("tag") == tag]
    if not facts:
        return None
    if period:
        at_period = [f for f in facts if f.get("period_end") == period]
        if at_period:
            return max(at_period, key=lambda f: f.get("period_end") or "")
        return None  # a fact at the wrong reporting context must not be silently returned
    return facts[0]


def extract_statement_rows(html: str) -> list[dict]:
    """Extract rendered table rows (label + cell text) from the statement tables.

    This is a best-effort extraction of the human-readable rows; each cell text is the
    displayed value, not the scaled XBRL fact.
    """
    rows: list[dict] = []
    for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr.group(1), re.DOTALL | re.IGNORECASE)
        if not cells:
            continue
        cleaned = []
        for c in cells:
            txt = re.sub(r"<[^>]+>", "", c)
            txt = re.sub(r"\s+", " ", txt).strip()
            if txt:
                cleaned.append(txt)
        if cleaned:
            rows.append({"cells": cleaned})
    return rows


def extract_note_excerpts(html: str, keywords: tuple[str, ...],
                          context_chars: int = 400) -> list[str]:
    """Extract plain-text passages around accounting-note keywords (debt/cash/lease)."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r" | |&", " ", text)
    text = re.sub(r"\s+", " ", text)
    excerpts: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        for m in re.finditer(re.escape(kw), text, re.IGNORECASE):
            start = max(0, m.start() - context_chars // 2)
            end = min(len(text), m.end() + context_chars // 2)
            snippet = text[start:end].strip()
            key = snippet[:120]
            if key not in seen:
                seen.add(key)
                excerpts.append(snippet)
            if len(excerpts) >= 20:
                return excerpts
    return excerpts


def filing_evidence(url: str, user_agent: str, tags: tuple[str, ...],
                    period: str | None = None,
                    note_keywords: tuple[str, ...] = ()) -> dict:
    """Retrieve inline XBRL facts + statement rows + note excerpts for the given tags."""
    html = fetch_filing(url, user_agent)
    contexts = extract_contexts(html)
    units = extract_units(html)
    facts = {t: lookup_fact(html, t, period) for t in tags}
    rows = extract_statement_rows(html)
    # Keep the rows that mention any requested tag keyword (label text near the fact).
    interesting = [r for r in rows if any(
        t.lower().replace("and", "") in " ".join(r["cells"]).lower() for t in tags)]
    excerpts = extract_note_excerpts(html, note_keywords) if note_keywords else []
    return {"url": url, "facts": {t: v for t, v in facts.items() if v is not None},
            "missing_tags": [t for t in tags if facts.get(t) is None],
            "statement_rows": interesting[:80],
            "note_excerpts": excerpts,
            "html_len": len(html)}
