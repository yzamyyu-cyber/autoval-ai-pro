"""Machine-readable reconciliation records (proposals + resolutions)."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone


def save_record(proposal: dict, out_dir: str) -> str:
    """Persist a proposal as a machine-readable JSON record. Returns the file path."""
    os.makedirs(out_dir, exist_ok=True)
    ticker = (proposal.get("ticker") or "UNKNOWN").upper()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(out_dir, f"{ticker}_{stamp}.json")
    record = dict(proposal)
    record.setdefault("record_utc", datetime.now(timezone.utc).isoformat())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, default=str, ensure_ascii=False)
    return path


def load_record(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_records(out_dir: str) -> list[str]:
    if not os.path.isdir(out_dir):
        return []
    return sorted(os.path.join(out_dir, n) for n in os.listdir(out_dir) if n.endswith(".json"))
