#!/usr/bin/env python3
"""One-shot migration: parse the inline team sections in index.html and
emit one Markdown file per member into _team/.

After running, the _team/*.md files become the source of truth; the
inline HTML in index.html can be replaced with a Liquid loop.

Usage:  python3 tools/extract_team.py
"""

from __future__ import annotations
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT  = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
OUT   = ROOT / "_team"

ROLE_ALIASES = {
    "phd student":         "PhD student",
    "phd_student":         "PhD student",
    "ph.d. student":       "PhD student",
    "invited phd student": "Invited PhD student",
    "postdoc":             "PostDoc",
    "research engineer":   "Research Engineer",
    "research path student": "Research path student",
    "prim project":        "PRIM project",
    "stage m1":            "Stage M1",
    "stage m2":            "Stage M2",
    "free stage":          "Free stage",
}


def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "member"


def normalize_role(raw: str) -> str:
    r = raw.strip().lower()
    for k, v in ROLE_ALIASES.items():
        if r.startswith(k):
            return v
    return raw.strip()


def parse_current(soup: BeautifulSoup) -> list[dict]:
    members = []
    for div in soup.select(".team-member"):
        h4 = div.find("h4")
        if not h4:
            continue
        img = div.find("img")
        deg = div.find("span", class_="deg")
        ems = div.find_all("em")

        role  = (deg.get_text(" ", strip=True) if deg else "").rstrip()
        topic = ems[0].get_text(" ", strip=True) if len(ems) >= 1 else ""

        co_supervisor = ""
        previously    = ""
        for em in ems[1:]:
            t = em.get_text(" ", strip=True)
            if not t:
                continue
            if t.lower().startswith("co-supervised with"):
                co_supervisor = t.split("with", 1)[1].strip()
            elif t.lower().startswith("previously"):
                previously = t.split(":", 1)[-1].strip()

        members.append({
            "status":        "current",
            "name":          h4.get_text(" ", strip=True),
            "photo":         (img.get("src") or "") if img else "",
            "role":          normalize_role(role),
            "topic":         topic,
            "co_supervisor": co_supervisor,
            "previously":    previously,
        })
    return members


def parse_former(soup: BeautifulSoup) -> list[dict]:
    """Parse the "Formerly advising" list. The HTML there has malformed
    <li> tags (no closing), so BeautifulSoup nests them all into the
    first <li>. We work around that by splitting the raw inner HTML on
    <h4>...</h4> blocks instead of trusting the <li> structure."""
    members = []
    h3 = soup.find(lambda t: t.name == "h3"
                   and "Formerly advising" in t.get_text())
    if not h3:
        return members
    ul = h3.find_next("ul")
    if not ul:
        return members

    raw = ul.decode_contents()
    # Strip HTML comments
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)

    # Split into segments, one per <h4>NAME</h4> ... up to the next <h4>
    pattern = re.compile(
        r"<h4>(?P<name>.*?)</h4>\s*\((?P<meta>[^)]+)\)(?P<body>.*?)"
        r"(?=<h4>|\Z)",
        flags=re.DOTALL | re.IGNORECASE,
    )

    for m in pattern.finditer(raw):
        name  = re.sub(r"\s+", " ", m.group("name")).strip()
        meta  = m.group("meta").strip()
        body  = m.group("body")
        role, period = _split_role_period(meta)
        body_md = _html_to_md(body)
        members.append({
            "status": "former",
            "name":   name,
            "role":   role,
            "period": period,
            "body":   body_md,
        })
    return members


_ROLE_REGEX = re.compile(
    r"^\s*(?P<role>"
    r"PostDoc|PhD\s*Student|Research\s*Engineer|Invited\s*PhD\s*student"
    r"|Research\s*path\s*student|PRIM\s*project|Stage\s*M1|Stage\s*M2"
    r"|Free\s*stage"
    r")\s*[,\s]\s*(?P<period>.+)$",
    flags=re.IGNORECASE,
)


def _split_role_period(meta: str) -> tuple[str, str]:
    m = _ROLE_REGEX.match(meta)
    if m:
        return normalize_role(m.group("role")), m.group("period").strip()
    # fallback: first token = role
    parts = meta.split(None, 1)
    if len(parts) == 2:
        return normalize_role(parts[0]), parts[1].strip()
    return normalize_role(meta), ""


def _html_to_md(s: str) -> str:
    """Light HTML -> Markdown conversion: links, breaks, br/li removal."""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</?li[^>]*>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<a\s+href=\"([^\"]+)\"[^>]*>(.*?)</a>",
               r"[\2](\1)", s, flags=re.IGNORECASE | re.DOTALL)
    s = re.sub(r"<[^>]+>", "", s)              # strip any leftover tags
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def yaml_str(s: str) -> str:
    s = (s or "").replace("\\", "\\\\").replace("\"", "\\\"")
    if not s:
        return '""'
    return f'"{s}"'


def write_member(m: dict) -> Path:
    slug = slugify(m["name"])
    front = ["---"]
    front.append(f'name: {yaml_str(m["name"])}')
    front.append(f'status: {m["status"]}')
    front.append(f'role: {yaml_str(m["role"])}')
    if m["status"] == "current":
        if m.get("photo"):  front.append(f'photo: {yaml_str(m["photo"])}')
        if m.get("topic"):  front.append(f'topic: {yaml_str(m["topic"])}')
        if m.get("co_supervisor"):
            front.append(f'co_supervisor: {yaml_str(m["co_supervisor"])}')
        if m.get("previously"):
            front.append(f'previously: {yaml_str(m["previously"])}')
    else:
        if m.get("period"):
            front.append(f'period: {yaml_str(m["period"])}')
    front.append("---")
    body = m.get("body") or ""
    out = "\n".join(front) + ("\n\n" + body if body else "") + "\n"

    path = OUT / f"{slug}.md"
    path.write_text(out, encoding="utf-8")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    soup = BeautifulSoup(INDEX.read_text(encoding="utf-8"), "html.parser")

    current = parse_current(soup)
    former  = parse_former(soup)

    for m in current + former:
        write_member(m)

    print(f"current: {len(current)}; former: {len(former)}; "
          f"total files: {len(current) + len(former)}")


if __name__ == "__main__":
    main()
