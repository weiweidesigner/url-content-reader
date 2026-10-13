---
name: url-content-reader
description: Read user-provided HTTP(S) URLs and extract title, description, readable text and links.
---

# URL Content Reader

Use `scripts/url_content_reader.py` when the user supplies URLs and asks to read, summarize, extract or analyze them. It reads given pages rather than discovering new sources; Kimi search is maintained separately.

Preserve the existing CLI and payload contract. Pass repeated `--url` or URL JSON through `--data`; use `--question`, `--timeout`, `--max-chars`, `--output` and `--payload-output` as needed. `--output` is HTML; `--payload-output` saves structured JSON. The reader returns extracted observations, not an LLM-written summary.

This package uses the Python standard library without credentials. Local host configuration, fetched user pages and logs must remain outside the repository.
