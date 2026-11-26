"""SEC retrieval helpers for the reconciliation agent.

Treats every retrieved document as UNTRUSTED data (plain text to inspect), never as
executable instructions. Reuses `autoval.sec` for companyfacts and provides filing-index,
alternative-tag and bounded filing-text access for the LLM investigation.
"""
from __future__ import annotations
import re
from urllib.request import Request, urlopen

from autoval.sec import fetch_json, FACTS_URL, sec_lookup

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"


def fetch_submissions(cik: int, user_agent: str) -> dict:
    req = Request(SUBMISSIONS.format(cik=cik), headers={"User-Agent": user_agent})
    import json
    return json.load(urlopen(req, timeout=30))


def latest_periodic(cik: int, user_agent: str, forms=("10-K", "10-Q")) -> dict | None:
    """Latest periodic filing (accession, primary document, dates) from the submissions index."""
    try:
        subs = fetch_submissions(cik, user_agent)
    except Exception:
        return None
    rec = subs.get("filings", {}).get("recent", {})
    forms_list = rec.get("form", [])
    accessions = rec.get("accessionNumber", [])
    docs = rec.get("primaryDocument", [])
    dates = rec.get("filingDate", [])
    report_dates = rec.get("reportDate", [""] * len(forms_list))
    for form, acc, doc, d, rd in zip(forms_list, accessions, docs, dates, report_dates):
        if form in forms:
            return {"form": form, "accession": acc, "primary_document": doc,
                    "filing_date": d, "report_date": rd,
                    "cik": cik}
    return None


def filing_url(cik, accession: str, primary_document: str) -> str:
    acc = accession.replace("-", "")
    return ARCHIVES.format(cik=cik, acc=acc, doc=primary_document)


def alternative_tags(facts: dict, keyword: str, taxonomy: str = "us-gaap") -> list[str]:
    """List tags under a taxonomy whose name contains `keyword` (case-insensitive)."""
    tags = facts.get("facts", {}).get(taxonomy, {})
    kw = keyword.lower()
    return sorted(t for t in tags if kw in t.lower())


def fetch_filing_text(url: str, user_agent: str, max_chars: int = 40000) -> str:
    """Fetch a filing HTML page and return stripped plain text (bounded)."""
    req = Request(url, headers={"User-Agent": user_agent})
    html = urlopen(req, timeout=60).read().decode("utf-8", "ignore")
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text[:max_chars]


def company_facts(ticker: str, user_agent: str) -> tuple[int, str, dict]:
    """Resolve CIK + name and fetch the full companyfacts JSON."""
    cik, name = sec_lookup(ticker, user_agent)
    facts = fetch_json(FACTS_URL.format(cik=cik), user_agent)
    return cik, name, facts
