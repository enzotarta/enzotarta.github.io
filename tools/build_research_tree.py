#!/usr/bin/env python3
"""Tag publications with research topics and emit _data/research_tree.json
for the D3 force-directed graph on /research.html.

Hybrid classifier:
  1. Fetch all of the author's works from OpenAlex (concepts + topics).
  2. Match each .bib paper to its OpenAlex record by normalized title or DOI.
  3. A paper is tagged with a topic if any of its OpenAlex concept/topic
     names contains a keyword from topics.yml::concept_keywords (case-
     insensitive substring), OR its title+venue matches the topic's regex.

OpenAlex is free and rate-limit-friendly; no API key required.

Reads:
  - _data/topics.yml
  - _data/publications/preprints.yml
  - _data/publications/main.yml
Writes:
  - _data/research_tree.json
"""

from __future__ import annotations
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT          = Path(__file__).resolve().parent.parent
TOPICS_FILE   = ROOT / "_data" / "topics.yml"
PUB_FILES     = [ROOT / "_data" / "publications" / "preprints.yml",
                 ROOT / "_data" / "publications" / "main.yml"]
OUT           = ROOT / "_data" / "research_tree.json"
OPENALEX_ID   = "A5046851981"
USER_AGENT    = "enzotarta.github.io/1.0 (mailto:enzo.tartaglione@telecom-paris.fr)"

OTHER = {"id": "other", "label": "Other", "color": "#94a3b8"}


# ---------- Loading -----------------------------------------------------------

def load_topics() -> list[dict]:
    with open(TOPICS_FILE, encoding="utf-8") as f:
        topics = yaml.safe_load(f) or []
    for t in topics:
        if t.get("regex"):
            t["_pattern"] = re.compile(t["regex"], flags=re.IGNORECASE)
        t["_keywords"] = [k.lower() for k in (t.get("concept_keywords") or [])]
    return topics


def load_papers() -> list[dict]:
    out = []
    for f in PUB_FILES:
        if not f.exists():
            print(f"warning: {f} missing", file=sys.stderr)
            continue
        with open(f, encoding="utf-8") as fh:
            out.extend(yaml.safe_load(fh) or [])
    return out


# ---------- OpenAlex ----------------------------------------------------------

def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_openalex_works(author_id: str) -> list[dict]:
    works = []
    cursor = "*"
    while cursor:
        params = {
            "filter":   f"author.id:{author_id}",
            "per-page": "200",
            "cursor":   cursor,
            "select":   "id,title,doi,concepts,topics",
        }
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        data = fetch(url)
        works.extend(data.get("results", []))
        cursor = data.get("meta", {}).get("next_cursor")
    return works


def normalize_title(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def index_works(works: list[dict]) -> tuple[dict, dict]:
    by_title, by_doi = {}, {}
    for w in works:
        labels: list[str] = []
        for c in w.get("concepts") or []:
            if c.get("display_name"):
                labels.append(c["display_name"])
        for t in w.get("topics") or []:
            if t.get("display_name"):
                labels.append(t["display_name"])
            sf = (t.get("subfield") or {}).get("display_name")
            if sf:
                labels.append(sf)
        entry = {"labels": [l.lower() for l in labels]}
        if w.get("title"):
            by_title[normalize_title(w["title"])] = entry
        if w.get("doi"):
            by_doi[w["doi"].lower().replace("https://doi.org/", "")] = entry
    return by_title, by_doi


# ---------- Classification ----------------------------------------------------

def assign_topics(paper: dict, topics: list[dict],
                  by_title: dict, by_doi: dict) -> tuple[list[str], str]:
    matched: set[str] = set()
    sources: set[str] = set()

    # 1) OpenAlex concept keywords
    oa = (by_title.get(normalize_title(paper.get("title", "")))
          or by_doi.get((paper.get("doi") or "").lower()))
    if oa:
        labels = oa["labels"]
        for t in topics:
            for kw in t["_keywords"]:
                if any(kw in l for l in labels):
                    matched.add(t["id"])
                    sources.add("openalex")
                    break

    # 2) Regex on title + venue
    haystack = ((paper.get("title") or "") + " "
                + (paper.get("venue") or "")).lower()
    for t in topics:
        pat = t.get("_pattern")
        if pat and pat.search(haystack):
            if t["id"] not in matched:
                sources.add("regex")
            matched.add(t["id"])

    src = ",".join(sorted(sources)) if sources else "none"
    return (sorted(matched) or ["other"]), src


# ---------- Tree --------------------------------------------------------------

def build_tree(topics: list[dict], papers: list[dict],
               by_title: dict, by_doi: dict) -> dict:
    topic_meta = [{"id": t["id"], "label": t["label"], "color": t["color"]}
                  for t in topics] + [OTHER.copy()]
    nodes = [{"id": "root", "type": "root", "label": "Research"}]
    nodes += [{"id": f"topic:{t['id']}", "type": "topic",
               "label": t["label"], "color": t["color"]}
              for t in topic_meta]
    links = [{"source": "root", "target": f"topic:{t['id']}"}
             for t in topic_meta]
    counts = {t["id"]: 0 for t in topic_meta}
    by_source: dict[str, int] = {}

    for p in papers:
        if not p.get("title"):
            continue
        pid = "paper:" + str(p.get("id") or p["title"][:24])
        matched, source = assign_topics(p, topics, by_title, by_doi)
        by_source[source] = by_source.get(source, 0) + 1
        nodes.append({
            "id":     pid,
            "type":   "paper",
            "label":  p["title"],
            "year":   p.get("year") or 0,
            "venue":  p.get("venue") or "",
            "url":    p.get("url") or "",
            "topics": matched,
        })
        for t in matched:
            links.append({"source": f"topic:{t}", "target": pid})
            counts[t] += 1

    # Drop topics with no papers
    empty = {tid for tid, n in counts.items() if n == 0}
    if empty:
        drop = {f"topic:{t}" for t in empty}
        nodes = [n for n in nodes if n["id"] not in drop]
        links = [l for l in links
                 if l["source"] not in drop and l["target"] not in drop]
        topic_meta = [t for t in topic_meta if t["id"] not in empty]

    return {
        "nodes":  nodes,
        "links":  links,
        "topics": topic_meta,
        "stats":  {
            "papers":     sum(1 for n in nodes if n["type"] == "paper"),
            "topics":     sum(1 for n in nodes if n["type"] == "topic"),
            "by_topic":   counts,
            "by_source":  by_source,
        },
    }


def main() -> None:
    topics = load_topics()
    papers = load_papers()

    print(f"fetching OpenAlex works for {OPENALEX_ID} ... ", end="", flush=True)
    works = fetch_openalex_works(OPENALEX_ID)
    print(f"{len(works)} works")
    by_title, by_doi = index_works(works)

    tree = build_tree(topics, papers, by_title, by_doi)
    OUT.write_text(json.dumps(tree, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")

    s = tree["stats"]
    print(f"Wrote {OUT.relative_to(ROOT)}: "
          f"{s['papers']} papers across {s['topics']} topics")
    for tid, n in sorted(s["by_topic"].items(), key=lambda kv: -kv[1]):
        print(f"  {tid:>16}: {n}")
    print(f"  match sources: {s['by_source']}")


if __name__ == "__main__":
    main()
