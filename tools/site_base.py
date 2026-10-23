"""Render this repository's README.md as a standalone GitHub Pages page.

    python tools/site.py            # writes index.html, and docs/method.html if there is one
    python tools/site.py --check    # verifies every referenced file exists, writes nothing

The pages are plain static HTML with the stylesheet inlined, so GitHub Pages
serves them with no build step - `.nojekyll` next to them says so explicitly.
Set the Pages source to the default branch, root folder, and the site is live.

Links back to the repository and across to the rest of the portfolio are read
from `git remote get-url origin`, so there is nothing to configure. If there is
no remote yet, those links are simply left out.

Requires: markdown-it-py (see requirements.txt).
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
METHOD = ROOT / "docs" / "method.md"

PORTFOLIO_REPO = "basketball-analytics"   # the index repo, if one exists

CSS = """
:root{
  --surface:#fcfcfb; --raised:#f4f3ef; --ink:#0b0b0b; --ink-2:#43423f; --ink-3:#7d7b74;
  --rule:#e3e2dc; --accent:#1c5cab; --mark:#eb6834;
}
@media (prefers-color-scheme: dark){
  :root{
    --surface:#14140f; --raised:#1e1e18; --ink:#f2f1ec; --ink-2:#c9c7bf; --ink-3:#8d8b83;
    --rule:#2e2e27; --accent:#7fb0f0; --mark:#f2895a;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--surface); color:var(--ink);
  font:400 17px/1.62 "Source Sans 3","Source Sans Pro",-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  font-feature-settings:"kern" 1;
}
.wrap{max-width:1020px;margin:0 auto;padding:0 22px}
.bar{border-bottom:1px solid var(--rule);background:var(--surface)}
.bar .wrap{display:flex;flex-wrap:wrap;gap:10px 22px;align-items:baseline;padding-top:16px;padding-bottom:15px}
.bar .slug{
  font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:12.5px;letter-spacing:.02em;color:var(--ink-2)
}
.bar nav{margin-left:auto;display:flex;gap:18px}
.bar a{
  font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:12.5px;color:var(--ink-3);text-decoration:none;border-bottom:1px solid transparent
}
.bar a:hover{color:var(--accent);border-bottom-color:var(--accent)}
main{padding:0 0 96px}
.col{max-width:700px}
h1{
  font-family:Archivo,"Helvetica Neue",Helvetica,Arial,sans-serif;
  font-weight:700;font-size:clamp(30px,5.4vw,46px);line-height:1.08;
  letter-spacing:-.022em;margin:54px 0 20px;max-width:640px
}
h2{
  font-family:Archivo,"Helvetica Neue",Helvetica,Arial,sans-serif;
  font-weight:600;font-size:22px;line-height:1.24;letter-spacing:-.012em;
  margin:52px 0 14px;max-width:700px
}
h3{font-family:Archivo,"Helvetica Neue",Helvetica,Arial,sans-serif;font-weight:600;
  font-size:18.5px;letter-spacing:-.008em;margin:40px 0 8px}
p.meta{font-size:14.5px;color:var(--ink-3);margin:-2px 0 16px}
p.meta a{border-bottom-color:transparent}
p.meta a:hover{border-bottom-color:currentColor}
p{margin:0 0 18px;max-width:700px}
p strong{font-weight:600}
a{color:var(--accent);text-decoration:none;border-bottom:1px solid rgba(28,92,171,.32)}
a:hover{border-bottom-color:currentColor}
hr{border:0;border-top:1px solid var(--rule);margin:46px 0}
ul,ol{margin:0 0 18px;padding-left:22px;max-width:700px}
li{margin:0 0 8px}
li>p{margin:0 0 8px}
code{
  font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:.86em;background:var(--raised);padding:.12em .34em;border-radius:3px
}
pre{
  background:var(--raised);border:1px solid var(--rule);border-radius:5px;
  padding:15px 17px;overflow-x:auto;margin:0 0 22px;max-width:820px
}
pre code{background:none;padding:0;font-size:13px;line-height:1.55}
em{color:var(--ink-2)}
.tw{overflow-x:auto;margin:0 0 26px;max-width:980px}
table{border-collapse:collapse;font-size:14.5px;min-width:100%}
th,td{padding:7px 15px 7px 0;text-align:left;border-bottom:1px solid var(--rule);white-space:nowrap}
th{
  font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
  font-size:11.5px;text-transform:uppercase;letter-spacing:.055em;
  color:var(--ink-3);font-weight:500;border-bottom-color:var(--ink-3);white-space:normal
}
td.num{text-align:right;font-variant-numeric:tabular-nums;padding-right:22px}
th.num{text-align:right;padding-right:22px}
tbody tr:last-child td{border-bottom:0}
figure{margin:30px 0 34px;max-width:980px}
figure img{display:block;width:100%;height:auto;border:1px solid var(--rule);border-radius:4px}
.foot{border-top:1px solid var(--rule);padding:22px 0 40px}
.foot .wrap{
  font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
  font-size:11.5px;color:var(--ink-3);display:flex;flex-wrap:wrap;gap:8px 20px
}
@media (max-width:560px){
  body{font-size:16px}
  .wrap{padding:0 16px}
  h1{margin-top:36px}
  th,td{padding-right:14px}
}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Archivo:wght@600;700&family=IBM+Plex+Mono:wght@400;500&'
         'family=Source+Sans+3:ital,wght@0,400;0,600;1,400&display=swap">')

NUMERIC = re.compile(r"^[−+\-]?[\d,]+(\.\d+)?%?(\s*\(\d+(st|nd|rd|th)\))?$")


def origin() -> tuple[str, str] | None:
    """(user, repo) from the git remote, or None if there isn't one."""
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    return (m.group(1), m.group(2)) if m else None


def align_numbers(body: str) -> str:
    """Right-align table cells that hold numbers. Purely cosmetic, but a column
    of figures that does not line up reads as sloppy, and these pages are mostly
    columns of figures."""
    def cell(m):
        tag, attrs, inner = m.group(1), m.group(2), m.group(3)
        text = re.sub(r"<[^>]+>", "", inner).strip()
        if text and NUMERIC.match(text):
            return f"<{tag}{attrs} class=\"num\">{inner}</{tag}>"
        return m.group(0)
    return re.sub(r"<(td|th)([^>]*)>(.*?)</\1>", cell, body, flags=re.S)


def mark_meta_lines(body: str) -> str:
    """Tag paragraphs that are nothing but links as navigation rather than prose.

    A line like "read the write-up - repository" is signposting, and it should
    not compete with the sentence under it. A paragraph qualifies only if it
    holds two or more links and no words of its own, which leaves ordinary
    prose containing a link alone."""
    def one(m):
        inner = m.group(1)
        if inner.count("<a ") < 2:
            return m.group(0)
        stripped = re.sub(r"<a\b.*?</a>", "", inner, flags=re.S)
        if re.sub(r"<[^>]+>|[\s&;#0-9a-z]*", "", stripped, flags=re.I) == "":
            return f'<p class="meta">{inner}</p>'
        return m.group(0)
    return re.sub(r"<p>(.*?)</p>", one, body, flags=re.S)


def render(md_text: str, slug: str, remote, depth: int = 0, method: bool = False) -> str:
    """`depth` is how many directories down the output sits, so relative links
    to the figures and to the sibling page resolve either way."""
    from markdown_it import MarkdownIt

    body = MarkdownIt("commonmark").enable("table").render(md_text)

    # Standalone images become figures; the alt text is already the caption in
    # the README, so it is not repeated underneath.
    body = re.sub(r"<p>(<img [^>]*>)</p>", r"<figure>\1</figure>", body)
    body = body.replace("<img ", '<img loading="lazy" ')
    body = re.sub(r"<table>", '<div class="tw"><table>', body)
    body = re.sub(r"</table>", "</table></div>", body)
    body = align_numbers(body)
    body = mark_meta_lines(body)

    # The first h1 becomes the page's own heading; everything else flows.
    m = re.search(r"<h1>(.*?)</h1>", body, flags=re.S)
    title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else slug
    lead = re.search(r"<p>(.*?)</p>", body, flags=re.S)
    desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", lead.group(1))).strip() if lead else ""

    up = "../" * depth
    body = body.replace('src="figures/', f'src="{up}figures/')

    nav = []
    if method:
        nav.append(f'<a href="{up}index.html">findings</a>' if depth
                   else '<a href="docs/method.html">method</a>')
    if remote:
        user, repo = remote
        nav.append(f'<a href="https://github.com/{user}/{repo}">repository</a>')
        if repo != PORTFOLIO_REPO:
            nav.append(f'<a href="https://{user}.github.io/{PORTFOLIO_REPO}/">all projects</a>')

    return (
        f'<!doctype html>\n<html lang="en">\n<head>\n'
        f'<meta charset="utf-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{html.escape(title)}</title>\n'
        f'<meta name="description" content="{html.escape(desc[:180])}">\n'
        f'{FONTS}\n<style>{CSS}</style>\n</head>\n<body>\n'
        f'<header class="bar"><div class="wrap"><span class="slug">{html.escape(slug)}</span>'
        f'<nav>{"".join(nav)}</nav></div></header>\n'
        f'<main><div class="wrap">\n{body}\n</div></main>\n'
        f'<footer class="foot"><div class="wrap"><span>{html.escape(slug)}</span>'
        f'<span>source, results and validation notes in the repository</span>'
        f'</div></footer>\n</body>\n</html>\n'
    )


def referenced_files(md_text: str) -> list[str]:
    return re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md_text) + \
        re.findall(r"`(figures/[^`]+|output/[^`]+|docs/[^`]+)`", md_text)


def check(md_text: str) -> int:
    missing = [p for p in referenced_files(md_text)
               if not p.startswith("http") and not (ROOT / p).exists()]
    for p in sorted(set(missing)):
        print(f"missing: {p}")
    print(f"{len(set(referenced_files(md_text)))} referenced paths, {len(set(missing))} missing")
    return 1 if missing else 0


def main() -> None:
    md_text = README.read_text(encoding="utf-8")
    if "--check" in sys.argv[1:]:
        raise SystemExit(check(md_text))

    remote, has_method = origin(), METHOD.exists()
    pages = [(md_text, ROOT / "index.html", 0)]
    if has_method:
        pages.append((METHOD.read_text(encoding="utf-8"), ROOT / "docs" / "method.html", 1))

    for text, out, depth in pages:
        out.write_text(render(text, ROOT.name, remote, depth, has_method), encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size / 1024:.0f} kB)")
    (ROOT / ".nojekyll").touch()


if __name__ == "__main__":
    main()
