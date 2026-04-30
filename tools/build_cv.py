#!/usr/bin/env python3
"""Build assets/pdf/cv.pdf from cv.md.

Strips the Jekyll YAML frontmatter, parses the markdown with mistune (3.x),
renders it to LaTeX through a custom renderer, splices the result into
tools/cv_template.tex at the __BODY__ marker, and runs pdflatex.

Usage:  python3 tools/build_cv.py
"""

from __future__ import annotations
import re
import shutil
import subprocess
import sys
from pathlib import Path

import mistune
from mistune.core import BaseRenderer

ROOT = Path(__file__).resolve().parent.parent
SRC_MD = ROOT / "cv.md"
TEMPLATE = ROOT / "tools" / "cv_template.tex"
BUILD_DIR = ROOT / "tools" / "build"
OUT_PDF = ROOT / "assets" / "pdf" / "cv.pdf"


_LATEX_REPL = {
    "\\": r"\textbackslash{}",
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def latex_escape(s: str) -> str:
    out = "".join(_LATEX_REPL.get(c, c) for c in s)
    return (out
            .replace("—", "---").replace("–", "--")
            .replace("“", "``").replace("”", "''")
            .replace("‘", "`").replace("’", "'")
            .replace("…", r"\ldots{}"))


class LatexRenderer(BaseRenderer):
    NAME = "latex"

    def render_token(self, token, state):
        method = getattr(self, token["type"], None)
        if not method:
            return ""
        return method(token, state)

    def render_tokens(self, tokens, state):
        return "".join(self.render_token(t, state) for t in tokens)

    def render_children(self, token, state):
        children = token.get("children") or []
        return self.render_tokens(children, state)

    # --- inline ---
    def text(self, token, state):
        return latex_escape(token.get("raw", ""))

    def emphasis(self, token, state):
        return r"\textit{" + self.render_children(token, state) + "}"

    def strong(self, token, state):
        return r"\textbf{" + self.render_children(token, state) + "}"

    def link(self, token, state):
        url = token["attrs"]["url"]
        body = self.render_children(token, state)
        url_safe = url.replace("#", r"\#").replace("%", r"\%")
        return r"\href{" + url_safe + "}{" + body + "}"

    def codespan(self, token, state):
        return r"\texttt{" + latex_escape(token.get("raw", "")) + "}"

    def linebreak(self, token, state):
        return r"\\ "

    def softbreak(self, token, state):
        return " "

    def inline_html(self, token, state):
        return ""

    # --- blocks ---
    def paragraph(self, token, state):
        return self.render_children(token, state) + "\n\n"

    def heading(self, token, state):
        level = token["attrs"]["level"]
        body = self.render_children(token, state)
        body = re.sub(r"\s*\{#[^}]+\}\s*$", "", body)  # strip kramdown id
        if level == 1:
            return ""
        if level == 2:
            return f"\n\\cvsection{{{body}}}\n"
        return f"\n\\subsection*{{{body}}}\n"

    def block_text(self, token, state):
        return self.render_children(token, state)

    def block_code(self, token, state):
        return "\\begin{verbatim}\n" + token.get("raw", "") + "\n\\end{verbatim}\n"

    def block_quote(self, token, state):
        return "\\begin{quote}\n" + self.render_children(token, state) + "\\end{quote}\n"

    def block_html(self, token, state):
        return ""

    def thematic_break(self, token, state):
        return "\\par\\hrule\\par\n"

    def blank_line(self, token, state):
        return ""

    def list(self, token, state):
        env = "enumerate" if token.get("attrs", {}).get("ordered") else "itemize"
        body = self.render_children(token, state)
        return f"\\begin{{{env}}}\n{body}\\end{{{env}}}\n\n"

    def list_item(self, token, state):
        body = self.render_children(token, state).strip()
        return f"\\item {body}\n"

    # --- tables (2-col "title | date") ---
    def table(self, token, state):
        rows = []
        for child in token.get("children", []):
            if child["type"] in ("table_head", "table_body"):
                for tr in child.get("children", []):
                    cells = [self.render_children(td, state).strip()
                             for td in tr.get("children", [])]
                    rows.append((child["type"], cells))

        body = [r[1] for r in rows if r[0] == "table_body"]

        out = ["\\begin{cventries}"]
        for cells in body:
            if len(cells) == 1 or (len(cells) >= 2 and cells[-1] == ""):
                out.append(f"\\cvgroup{{{cells[0]}}}")
            else:
                left = cells[0]
                right = cells[-1]
                out.append(f"\\cventry{{{left}}}{{{right}}}")
        out.append("\\end{cventries}\n")
        return "\n".join(out)

    def table_head(self, token, state): return ""
    def table_body(self, token, state): return ""
    def table_row(self, token, state):  return ""
    def table_cell(self, token, state): return self.render_children(token, state)


def strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[end + 4 :].lstrip("\n")
    return text


def strip_kramdown_ids(text: str) -> str:
    # remove {#anchor} markers at end of heading lines (kramdown-only syntax)
    return re.sub(r"^(#+\s.+?)\s*\{#[\w-]+\}\s*$", r"\1", text, flags=re.M)


def render_latex_body(md_path: Path) -> str:
    raw = strip_kramdown_ids(strip_frontmatter(md_path.read_text(encoding="utf-8")))
    md = mistune.create_markdown(renderer=LatexRenderer(), plugins=["table"])
    return md(raw)


def run_pdflatex(tex_path: Path) -> None:
    for _ in range(2):
        proc = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=tex_path.parent,
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout[-4000:] + "\n" + proc.stderr[-2000:] + "\n")
            raise SystemExit(f"pdflatex failed (exit {proc.returncode})")


def main() -> None:
    body = render_latex_body(SRC_MD)
    template = TEMPLATE.read_text(encoding="utf-8")
    if "__BODY__" not in template:
        raise SystemExit("Template missing __BODY__ marker")
    full = template.replace("__BODY__", body)

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    tex = BUILD_DIR / "cv.tex"
    tex.write_text(full, encoding="utf-8")

    run_pdflatex(tex)

    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BUILD_DIR / "cv.pdf", OUT_PDF)
    print(f"Wrote {OUT_PDF.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
