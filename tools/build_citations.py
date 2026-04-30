#!/usr/bin/env python3
"""Fetch Google Scholar author stats via SerpAPI and write
_data/citations.json for the publications page to render.

Reads SERPAPI_KEY from the environment; fails loudly if missing.

Usage:  SERPAPI_KEY=... python3 tools/build_citations.py [scholar_id]
"""

from __future__ import annotations
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_data" / "citations.json"
DEFAULT_SCHOLAR_ID = "uKuvN64AAAAJ"


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def extract_table_value(table: list[dict], key: str) -> int:
    for row in table or []:
        if key in row:
            v = row[key]
            return int(v.get("all", 0)) if isinstance(v, dict) else int(v or 0)
    return 0


def main() -> None:
    api_key = os.getenv("SERPAPI_KEY", "").strip()
    if not api_key:
        sys.exit("SERPAPI_KEY env var not set. Get one at https://serpapi.com/")

    scholar_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCHOLAR_ID
    params = {
        "engine":    "google_scholar_author",
        "author_id": scholar_id,
        "hl":        "en",
        "api_key":   api_key,
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    data = fetch(url)

    cited_by = data.get("cited_by", {}) or {}
    table    = cited_by.get("table", []) or []
    graph    = cited_by.get("graph", []) or []

    cited_by_count = extract_table_value(table, "citations")
    h_index        = extract_table_value(table, "h_index")
    i10_index      = extract_table_value(table, "i10_index")

    if graph:
        graph = sorted(graph, key=lambda g: g.get("year", 0))
        first, last = graph[0]["year"], graph[-1]["year"]
        by_year = {int(g["year"]): int(g.get("citations", 0)) for g in graph}
        years = list(range(first, last + 1))
        cites = [by_year.get(y, 0) for y in years]
    else:
        years, cites = [], []

    payload = {
        "author":            data.get("author", {}).get("name", ""),
        "scholar_id":        scholar_id,
        "scholar_url":       f"https://scholar.google.com/citations?user={scholar_id}",
        "cited_by_count":    cited_by_count,
        "h_index":           h_index,
        "i10_index":         i10_index,
        "years":             years,
        "citations_by_year": cites,
        "updated":           date.today().isoformat(),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: "
          f"{cited_by_count} citations, h={h_index}, i10={i10_index}, "
          f"{len(years)} years")


if __name__ == "__main__":
    main()
