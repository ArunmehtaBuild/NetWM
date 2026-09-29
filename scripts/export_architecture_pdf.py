"""Export docs/architecture.md to docs/architecture.pdf (the PS asks for at most 2 pages), offline.

    python scripts/export_architecture_pdf.py

Converts the document's Markdown subset (headings, paragraphs, nested lists, tables, one code block,
bold and code spans, links) to HTML with the standard library, prints it to PDF with a local Edge or
Chrome in headless mode, and fails if the PDF runs past ``--max-pages``. No package is installed and
nothing is downloaded.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "msedge", "google-chrome", "chromium", "chrome"]
CSS = """
@page { size: A4; margin: 12mm 13mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 8.6pt; line-height: 1.28; color: #111; }
h1 { font-size: 14pt; margin: 0 0 2pt; } h2 { font-size: 10.4pt; margin: 7pt 0 2pt; border-bottom: 1px solid #bbb; }
p { margin: 2pt 0; } ul, ol { margin: 1pt 0 2pt 15pt; padding: 0; } li { margin: 0.5pt 0; }
pre { font-family: Consolas, monospace; font-size: 6.6pt; line-height: 1.15; background: #f4f4f4; padding: 4pt; margin: 4pt 0; white-space: pre; }
code { font-family: Consolas, monospace; font-size: 8pt; }
table { border-collapse: collapse; margin: 3pt 0; } th, td { border: 1px solid #bbb; padding: 1.5pt 5pt; }
th { background: #eee; } td.num { text-align: right; }
"""


def inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", t)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)


def to_html(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    i, list_stack, para = 0, [], []

    def close_para():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    def close_lists(level: int = -1):
        while list_stack and list_stack[-1][0] > level:
            out.append(f"</li></{list_stack.pop()[1]}>")

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            close_para(); close_lists()
            block = []
            i += 1
            while not lines[i].startswith("```"):
                block.append(html.escape(lines[i])); i += 1
            out.append("<pre>" + "\n".join(block) + "</pre>")
        elif line.startswith("#"):
            close_para(); close_lists()
            n = len(line) - len(line.lstrip("#"))
            out.append(f"<h{n}>{inline(line[n:].strip())}</h{n}>")
        elif line.startswith("|"):
            close_para(); close_lists()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            aligns = ["num" if c.endswith(":") else "" for c in rows[1]]
            out.append("<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr>")
            for r in rows[2:]:
                out.append("<tr>" + "".join(f'<td class="{a}">{inline(c)}</td>' for c, a in zip(r, aligns)) + "</tr>")
            out.append("</table>")
            continue
        elif re.match(r"^\s*(- |\d+\. )", line):
            close_para()
            indent = len(line) - len(line.lstrip())
            kind = "ol" if re.match(r"^\s*\d+\. ", line) else "ul"
            text = re.sub(r"^\s*(- |\d+\. )", "", line)
            if list_stack and list_stack[-1][0] == indent:
                out.append("</li><li>" + inline(text))
            elif list_stack and list_stack[-1][0] > indent:
                close_lists(indent)
                out.append("</li><li>" + inline(text))
            else:
                out.append(f"<{kind}><li>" + inline(text))
                list_stack.append((indent, kind))
        elif line.strip() == "":
            close_para()
            if not (i + 1 < len(lines) and re.match(r"^\s*(- |\d+\. )", lines[i + 1])):
                close_lists()
        elif list_stack and line.startswith(" "):
            out[-1] += " " + inline(line.strip())  # a list item's continuation line
        else:
            para.append(line.strip())
        i += 1
    close_para(); close_lists()
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(out)}</body></html>"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", default=str(ROOT / "docs" / "architecture.md"))
    ap.add_argument("--pdf", default=str(ROOT / "docs" / "architecture.pdf"))
    ap.add_argument("--max-pages", type=int, default=2)
    args = ap.parse_args()
    browser = next((b for b in BROWSERS if Path(b).exists() or shutil.which(b)), None)
    if browser is None:
        raise SystemExit("no Edge or Chrome found to print the PDF")
    pdf = Path(args.pdf).resolve()
    pdf.unlink(missing_ok=True)
    # Edge leaves its profile busy for a moment after it exits, so the folder's cleanup may fail harmlessly
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        page = Path(tmp) / "architecture.html"
        page.write_text(to_html(Path(args.md).read_text(encoding="utf-8")), encoding="utf-8")
        # a profile of its own: a browser that is already open would otherwise take the call and write nothing
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
                        f"--user-data-dir={Path(tmp) / 'profile'}", f"--print-to-pdf={pdf}",
                        page.resolve().as_uri()], check=True, capture_output=True, timeout=180)
        # the launcher can return before the headless instance has written the file
        deadline = time.time() + 60
        while not (pdf.exists() and pdf.stat().st_size > 0) and time.time() < deadline:
            time.sleep(0.5)
        time.sleep(1.0)
    if not pdf.exists():
        raise SystemExit("the browser wrote no PDF")
    pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))
    print(f"{args.pdf}: {pages} page(s)")
    if pages > args.max_pages:
        raise SystemExit(f"{pages} pages: over the {args.max_pages}-page limit")


if __name__ == "__main__":
    main()
