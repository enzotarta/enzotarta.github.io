#!/usr/bin/env python3
"""Fetch OpenAlex per-year publication and citation counts and write
_data/citations.json for the site to render as a Scholar-style chart.

Usage:  python3 tools/build_citations.py [openalex_id]
"""

from __future__ import annotations
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_data" / "citations.json"
DEFAULT_ID = "A5046851981"
USER_AGENT = "enzotarta.github.io/1.0 (mailto:enzo.tartaglione@telecom-paris.fr)"


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    aid = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ID
    data = fetch(f"https://api.openalex.org/authors/{aid}")
    counts = sorted(data.get("counts_by_year", []), key=lambda c: c["year"])

    if counts:
        years = list(range(counts[0]["year"], counts[-1]["year"] + 1))
        by_year = {c["year"]: c for c in counts}
        works  = [int(by_year.get(y, {}).get("works_count", 0))    for y in years]
        cites  = [int(by_year.get(y, {}).get("cited_by_count", 0)) for y in years]
    else:
        years, works, cites = [], [], []

    payload = {
        "author":           data.get("display_name", ""),
        "openalex_id":      aid,
        "scholar_url":      "https://scholar.google.com/citations?user=uKuvN64AAAAJ",
        "works_count":      int(data.get("works_count", 0)),
        "cited_by_count":   int(data.get("cited_by_count", 0)),
        "h_index":          int(data.get("summary_stats", {}).get("h_index", 0)),
        "i10_index":        int(data.get("summary_stats", {}).get("i10_index", 0)),
        "years":            years,
        "works_by_year":    works,
        "citations_by_year": cites,
        "updated":          date.today().isoformat(),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: "
          f"{payload['works_count']} works, {payload['cited_by_count']} citations, "
          f"h={payload['h_index']}, i10={payload['i10_index']}")


if __name__ == "__main__":
    main()
