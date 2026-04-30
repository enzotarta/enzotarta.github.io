#!/usr/bin/env python3
"""Fetch publication .bib files from BibBase, parse, and write structured
YAML to _data/publications/ for Jekyll to render.

Each output file is a list of entries (newest first) with normalized fields:
  - id, type, title, authors, venue, year, month, url, doi, bibtex

Usage:  python3 tools/build_publications.py
"""

from __future__ import annotations
import re
import sys
import urllib.request
from pathlib import Path

import bibtexparser
from bibtexparser.bparser import BibTexParser

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "_data" / "publications"

SOURCES = {
    "preprints": "https://bibbase.org/f/eigNBhSMoESt5Ygkm/preprints.bib",
    "main":      "https://bibbase.org/f/eigNBhSMoESt5Ygkm/main.bib",
    "patents":   "https://bibbase.org/f/eigNBhSMoESt5Ygkm/patents.bib",
    "datasets":  "https://bibbase.org/f/eigNBhSMoESt5Ygkm/datasets.bib",
}

VENUE_FIELDS = ("booktitle", "journal", "school", "institution", "publisher", "howpublished")
LATEX_REPL = [
    (r"\&", "&"), (r"\%", "%"), (r"\$", "$"), (r"\#", "#"), (r"\_", "_"),
    (r"\textquotesingle", "'"), (r"\textquotedblleft", "“"),
    (r"\textquotedblright", "”"),
    ("--", "–"), ("---", "—"),
    ("~", " "),
]


def clean_latex(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\{\\['`\"^~=.cvub]\s*([a-zA-Z])\}", r"\1", s)
    s = re.sub(r"\\['`\"^~=.cvub]\{([a-zA-Z])\}", r"\1", s)
    for pat, rep in LATEX_REPL:
        s = s.replace(pat, rep)
    s = s.replace("{", "").replace("}", "")
    return s.strip()


def split_authors(raw: str) -> list[str]:
    if not raw:
        return []
    parts = [p.strip() for p in re.split(r"\s+and\s+", raw)]
    out = []
    for p in parts:
        if "," in p:
            last, _, first = p.partition(",")
            name = f"{first.strip()} {last.strip()}"
        else:
            name = p
        out.append(clean_latex(name))
    return out


def normalize_entry(e: dict) -> dict:
    venue = ""
    for f in VENUE_FIELDS:
        if e.get(f):
            venue = clean_latex(e[f])
            break
    year = (e.get("year") or "").strip()
    try:
        year_int = int(re.search(r"\d{4}", year).group(0))
    except Exception:
        year_int = 0

    url = (e.get("url") or e.get("link") or "").strip()
    doi = (e.get("doi") or "").strip()
    if not url and doi:
        url = f"https://doi.org/{doi}"

    return {
        "id": e.get("ID", "") or e.get("id", ""),
        "type": e.get("ENTRYTYPE", "misc"),
        "title": clean_latex(e.get("title", "")),
        "authors": split_authors(e.get("author", "")),
        "venue": venue,
        "year": year_int,
        "url": url,
        "doi": doi,
    }


_MONTH_FULL = {
    "january": "jan", "february": "feb", "march": "mar", "april": "apr",
    "june": "jun", "july": "jul", "august": "aug", "september": "sep",
    "october": "oct", "november": "nov", "december": "dec",
}


def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def normalize_months(text: str) -> str:
    # bibtexparser only recognizes 3-letter month macros; rewrite full names
    def sub(m):
        return m.group(1) + _MONTH_FULL[m.group(2).lower()] + m.group(3)
    pat = r"(month\s*=\s*)(" + "|".join(_MONTH_FULL) + r")(\s*[,#}\n])"
    return re.sub(pat, sub, text, flags=re.IGNORECASE)


def parse_bib(text: str) -> list[dict]:
    text = normalize_months(text)
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    db = bibtexparser.loads(text, parser=parser)
    return [normalize_entry(e) for e in db.entries]


def to_yaml(entries: list[dict]) -> str:
    """Hand-rolled YAML emitter — pyyaml isn't always installed."""
    out = []
    for e in entries:
        out.append("- id: " + yaml_str(e["id"]))
        out.append("  type: " + yaml_str(e["type"]))
        out.append("  title: " + yaml_str(e["title"]))
        out.append("  year: " + str(e["year"]))
        out.append("  venue: " + yaml_str(e["venue"]))
        out.append("  url: " + yaml_str(e["url"]))
        out.append("  doi: " + yaml_str(e["doi"]))
        if e["authors"]:
            out.append("  authors:")
            for a in e["authors"]:
                out.append("    - " + yaml_str(a))
        else:
            out.append("  authors: []")
    return "\n".join(out) + "\n"


def yaml_str(s: str) -> str:
    if s is None:
        return '""'
    s = str(s)
    needs_quote = (not s) or any(c in s for c in ":#&*?|>!%@`") or s.strip() != s
    if needs_quote or s.lower() in ("yes", "no", "true", "false", "null", "~"):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        try:
            print(f"fetching {name} ... ", end="", flush=True)
            text = fetch(url)
            entries = parse_bib(text)
            entries.sort(key=lambda e: (-e["year"], e["title"].lower()))
            (OUT_DIR / f"{name}.yml").write_text(to_yaml(entries), encoding="utf-8")
            print(f"{len(entries)} entries")
        except Exception as exc:
            print(f"FAILED: {exc}", file=sys.stderr)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
