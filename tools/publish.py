"""Render standalone article documents, retaining figure captions and source links."""

import base64, html, re
import markdown
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

CSS = """body{margin:0;color:#172d45;background:#fff;font-family:Georgia,serif;font-size:18px;line-height:1.65}article{max-width:820px;margin:64px auto;padding:0 28px 60px}h1{font-family:Arial,sans-serif;font-size:42px;line-height:1.14;letter-spacing:-1px;margin-bottom:24px}h2{font-family:Arial,sans-serif;font-size:25px;line-height:1.3;margin-top:42px}a{color:#176b87;text-underline-offset:3px}img{width:100%;height:auto;display:block;margin:32px 0}code{font-family:monospace;font-size:.85em;overflow-wrap:anywhere;background:#f1f4f6;padding:2px 4px}pre{white-space:pre-wrap;padding:16px;background:#f1f4f6}table{border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:15px}th,td{padding:10px;border-bottom:1px solid #dde3e8;text-align:left}strong{font-weight:700}@media(max-width:600px){article{margin:28px auto;padding:0 18px 40px}h1{font-size:32px}body{font-size:17px}}@media print{article{margin:0;max-width:none}h2{break-after:avoid}img{break-inside:avoid}a{color:inherit}}"""


def run():
    for path in sorted((ROOT / "reports").glob("*.md")):
        source = path.read_text()
        title = source.splitlines()[0].lstrip("# ")
        body = markdown.markdown(source, extensions=["tables", "fenced_code"])

        def embed(m):
            image = (path.parent / m.group(1)).resolve()
            return (
                'src="data:image/png;base64,'
                + base64.b64encode(image.read_bytes()).decode()
                + '"'
            )

        body = re.sub(r'src="([^\"]+\.png)"', embed, body)
        output = (
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="author" content="Joseph Smarrelli"><title>'
            + html.escape(title)
            + "</title><style>"
            + CSS
            + "</style></head><body><article>"
            + body
            + "</article></body></html>"
        )
        path.with_suffix(".html").write_text(output)
    return len(list((ROOT / "reports").glob("*.md")))


if __name__ == "__main__":
    print(run(), "articles exported")
