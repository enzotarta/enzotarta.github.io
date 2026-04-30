#!/usr/bin/env python3
"""Tag publications with research topics and emit _data/research_tree.json
for the D3 force-directed graph on /research.html.

Reads:
  - _data/topics.yml         (topic id, label, color, regex)
  - _data/publications/preprints.yml
  - _data/publications/main.yml

Writes:
  - _data/research_tree.json  ({nodes, links, topics, stats})

Usage:  python3 tools/build_research_tree.py
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TOPICS_FILE = ROOT / "_data" / "topics.yml"
PUB_FILES   = [ROOT / "_data" / "publications" / "preprints.yml",
               ROOT / "_data" / "publications" / "main.yml"]
OUT         = ROOT / "_data" / "research_tree.json"

OTHER = {"id": "other", "label": "Other", "color": "#94a3b8",
         "regex": None}


def load_topics() -> list[dict]:
    with open(TOPICS_FILE, encoding="utf-8") as f:
        topics = yaml.safe_load(f) or []
    for t in topics:
        t["pattern"] = re.compile(t["regex"], flags=re.IGNORECASE)
    return topics


def load_papers() -> list[dict]:
    out = []
    for f in PUB_FILES:
        if not f.exists():
            print(f"warning: {f} missing — skipping", file=sys.stderr)
            continue
        with open(f, encoding="utf-8") as fh:
            out.extend(yaml.safe_load(fh) or [])
    return out


def assign_topics(paper: dict, topics: list[dict]) -> list[str]:
    haystack = " ".join([paper.get("title") or "",
                         paper.get("venue") or ""])
    matched = [t["id"] for t in topics if t["pattern"].search(haystack)]
    return matched or ["other"]


def build_tree(topics: list[dict], papers: list[dict]) -> dict:
    topic_meta = [{"id": t["id"], "label": t["label"], "color": t["color"]}
                  for t in topics] + [OTHER.copy()]

    nodes  = [{"id": "root", "type": "root",  "label": "Research"}]
    nodes += [{"id": f"topic:{t['id']}", "type": "topic",
               "label": t["label"], "color": t["color"]}
              for t in topic_meta]
    links  = [{"source": "root", "target": f"topic:{t['id']}"}
              for t in topic_meta]
    counts = {t["id"]: 0 for t in topic_meta}

    for p in papers:
        if not p.get("title"):
            continue
        pid = "paper:" + str(p.get("id") or p["title"][:24])
        matched = assign_topics(p, topics)
        nodes.append({
            "id":      pid,
            "type":    "paper",
            "label":   p["title"],
            "year":    p.get("year") or 0,
            "venue":   p.get("venue") or "",
            "url":     p.get("url") or "",
            "topics":  matched,
        })
        for t in matched:
            links.append({"source": f"topic:{t}", "target": pid})
            counts[t] += 1

    # drop empty topics — they'd be lonely orbs with no papers
    empty = {tid for tid, n in counts.items() if n == 0}
    if empty:
        topic_ids_to_drop = {f"topic:{t}" for t in empty}
        nodes = [n for n in nodes if n["id"] not in topic_ids_to_drop]
        links = [l for l in links
                 if l["source"] not in topic_ids_to_drop
                 and l["target"] not in topic_ids_to_drop]
        topic_meta = [t for t in topic_meta if t["id"] not in empty]

    return {
        "nodes":  nodes,
        "links":  links,
        "topics": topic_meta,
        "stats":  {"papers": sum(1 for n in nodes if n["type"] == "paper"),
                    "topics": sum(1 for n in nodes if n["type"] == "topic"),
                    "by_topic": counts},
    }


def main() -> None:
    topics = load_topics()
    papers = load_papers()
    tree   = build_tree(topics, papers)
    OUT.write_text(json.dumps(tree, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    s = tree["stats"]
    print(f"Wrote {OUT.relative_to(ROOT)}: "
          f"{s['papers']} papers across {s['topics']} topics")
    for tid, n in s["by_topic"].items():
        print(f"  {tid:>16}: {n}")


if __name__ == "__main__":
    main()
