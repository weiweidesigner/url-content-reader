#!/usr/bin/env python3
"""Fetch and extract readable text from one or more URLs."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_stack: list[str] = []
        self._title_parts: list[str] = []
        self._body_parts: list[str] = []
        self._links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_link_text: list[str] = []
        self._in_title = False
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript", "svg", "canvas", "template"}:
            self._skip_stack.append(tag)
            return
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").strip().lower()
            content = attrs_dict.get("content", "").strip()
            if name and content:
                self.meta[name] = content
        if tag == "a" and attrs_dict.get("href"):
            self._current_href = attrs_dict["href"]
            self._current_link_text = []
        if tag in {"p", "div", "section", "article", "header", "footer", "li", "tr", "h1", "h2", "h3", "h4", "br"}:
            self._body_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()
            return
        if tag == "a" and self._current_href:
            text = normalize_whitespace(" ".join(self._current_link_text))
            if text:
                self._links.append({"text": text[:160], "url": self._current_href})
            self._current_href = None
            self._current_link_text = []
        if tag in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._body_parts.append("\n")
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_stack:
            return
        text = normalize_whitespace(data)
        if not text:
            return
        if self._in_title:
            self._title_parts.append(text)
        self._body_parts.append(text)
        self._body_parts.append(" ")
        if self._current_href:
            self._current_link_text.append(text)

    @property
    def title(self) -> str:
        return normalize_whitespace(" ".join(self._title_parts))

    @property
    def text(self) -> str:
        text = "\n".join(normalize_whitespace(part) for part in "".join(self._body_parts).splitlines())
        lines = [line for line in (normalize_whitespace(line) for line in text.splitlines()) if line]
        deduped: list[str] = []
        seen: set[str] = set()
        for line in lines:
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(line)
        return "\n".join(deduped)

    @property
    def links(self) -> list[dict[str, str]]:
        return self._links


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def absolute_url(base_url: str, value: str) -> str:
    return urllib.parse.urljoin(base_url, value)


def fetch_url(url: str, timeout: float) -> tuple[str, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        raw = response.read(5_000_000)
        charset_match = re.search(r"charset=([\w.-]+)", content_type, re.I)
        charset = charset_match.group(1) if charset_match else "utf-8"
        try:
            text = raw.decode(charset, errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
        return text, content_type, response.geturl()


def extract_url(url: str, timeout: float, max_chars: int) -> dict[str, Any]:
    raw_html, content_type, final_url = fetch_url(url, timeout)
    if "html" not in content_type.lower() and "<html" not in raw_html[:1000].lower():
        text = normalize_whitespace(raw_html)
        return {
            "url": url,
            "finalUrl": final_url,
            "contentType": content_type,
            "title": "",
            "description": "",
            "text": text[:max_chars],
            "links": [],
            "truncated": len(text) > max_chars,
        }
    parser = TextExtractor()
    parser.feed(raw_html)
    parser.close()
    title = parser.title or parser.meta.get("og:title") or parser.meta.get("twitter:title") or ""
    description = parser.meta.get("description") or parser.meta.get("og:description") or parser.meta.get("twitter:description") or ""
    text = parser.text
    links = [
        {"text": item["text"], "url": absolute_url(final_url, item["url"])}
        for item in parser.links[:40]
    ]
    return {
        "url": url,
        "finalUrl": final_url,
        "contentType": content_type,
        "title": normalize_whitespace(title),
        "description": normalize_whitespace(description),
        "text": text[:max_chars],
        "links": links,
        "truncated": len(text) > max_chars,
    }


def render_html(payload: dict[str, Any]) -> str:
    items = payload.get("results") if isinstance(payload.get("results"), list) else []
    blocks = []
    for item in items:
        title = html.escape(str(item.get("title") or item.get("finalUrl") or item.get("url") or "Untitled"))
        url = html.escape(str(item.get("finalUrl") or item.get("url") or ""))
        text = html.escape(str(item.get("text") or ""))
        description = html.escape(str(item.get("description") or ""))
        blocks.append(
            f"<article><h2>{title}</h2><a href=\"{url}\" target=\"_blank\" rel=\"noreferrer\">{url}</a>"
            f"{f'<p class=\"desc\">{description}</p>' if description else ''}<pre>{text}</pre></article>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>URL Content Reader</title>
<style>
body{{margin:0;padding:18px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;color:#17202b;background:#fff}}
main{{display:grid;gap:18px}}
article{{display:grid;gap:8px;border-bottom:1px solid #eef1f5;padding-bottom:16px}}
h1,h2,p{{margin:0}}
h1{{font-size:20px}}h2{{font-size:17px}}a{{color:#2863f4;overflow-wrap:anywhere}}.desc{{color:#667085}}
pre{{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;color:#475467;font-size:13px;line-height:1.55}}
</style>
</head>
<body><main><h1>URL Content Reader</h1>{''.join(blocks) or '<p>No readable content.</p>'}</main></body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Read readable text from URLs.")
    parser.add_argument("--url", action="append", default=[], help="URL to read. Can repeat.")
    parser.add_argument("--data", help="JSON array/string containing URLs.")
    parser.add_argument("--question", default="")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--max-chars", type=int, default=12000)
    parser.add_argument("--output", required=True)
    parser.add_argument("--payload-output")
    parser.add_argument("--format", choices=["json"], default="json")
    args, _ = parser.parse_known_args()

    urls = list(args.url)
    if args.data:
        try:
            parsed = json.loads(args.data)
            if isinstance(parsed, str):
                urls.append(parsed)
            elif isinstance(parsed, list):
                urls.extend(str(item) for item in parsed)
        except json.JSONDecodeError:
            urls.append(args.data)
    urls = [url.strip() for url in urls if re.match(r"https?://", str(url).strip(), re.I)]
    if not urls:
        raise SystemExit("url_content_reader.py requires at least one http(s) --url.")

    results = []
    errors = []
    for url in urls[:8]:
        try:
            results.append(extract_url(url, args.timeout, max(1000, args.max_chars)))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append({"url": url, "error": str(exc)})
    payload = {
        "type": "url-content-reader",
        "query": args.question,
        "urls": urls,
        "results": results,
        "errors": errors,
        "article_count": len(results),
        "sources": [
            {"title": item.get("title") or item.get("finalUrl"), "url": item.get("finalUrl") or item.get("url"), "summary": item.get("description") or ""}
            for item in results
        ],
    }
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(payload), encoding="utf-8")
    if args.payload_output:
        Path(args.payload_output).expanduser().resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output_path), "count": len(results)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
