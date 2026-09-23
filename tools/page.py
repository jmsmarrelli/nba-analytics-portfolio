"""Render README.md as this repository's GitHub Pages front page.

    python tools/page.py

Links to the finished articles point at their standalone HTML versions; links
to source files point at the repository on GitHub. Writes index.html and
.nojekyll at the repository root.
"""
import re, sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_base as S

ROOT = Path(__file__).resolve().parents[1]
S.ROOT = ROOT


def rewrite(md: str, user: str, repo: str) -> str:
    def link(m):
        text, target = m.group(1), m.group(2)
        if target.startswith(("http", "#", "mailto:")):
            return m.group(0)
        path, _, frag = target.partition("#")
        if re.match(r"reports/[^/]+\.md$", path) and (ROOT / path.replace(".md", ".html")).exists():
            new = path[:-3] + ".html"
        elif (ROOT / path).is_dir():
            new = f"https://github.com/{user}/{repo}/tree/main/{path.rstrip('/')}"
        else:
            new = f"https://github.com/{user}/{repo}/blob/main/{path}"
        return f"[{text}]({new}{'#' + frag if frag else ''})"
    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)", link, md)


def main() -> None:
    remote = S.origin()
    md = (ROOT / "README.md").read_text(encoding="utf-8")
    if remote:
        md = rewrite(md, *remote)
    html = S.render(md, ROOT.name, remote, 0, False)
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    (ROOT / ".nojekyll").touch()
    print(f"wrote index.html ({len(html) / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
