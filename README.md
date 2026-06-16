# Markdown Link PageRank

A dependency-free Python utility that builds a graph from Markdown links and ranks the most central notes with PageRank.

It is designed for public-safe knowledge-base demos: local files in, ranked Markdown/JSON reports out. It does not call external services, require credentials, or ship any private workspace data.

## What it demonstrates

- Obsidian-style wikilink parsing: `[[Project Hub]]`, aliases, headings, and block references
- Standard Markdown `.md` link parsing
- Link-target resolution by exact path or unique basename
- Global PageRank over a directed note graph
- Optional keyword-personalized PageRank for topic-focused navigation
- Markdown and JSON report output
- Unit tests and CLI smoke checks with a synthetic sample vault

## Quick start

```bash
git clone https://github.com/thefiredev-cloud/markdown-link-pagerank.git
cd markdown-link-pagerank
python3 -m unittest discover -s tests
python3 src/markdown_link_pagerank.py \
  --root examples/sample-vault \
  --output /tmp/markdown-link-pagerank-report.md \
  --json /tmp/markdown-link-pagerank-report.json \
  --keywords "architecture,decision,index" \
  --limit 5
```

## Repository layout

```text
.
├── docs/architecture.md             # Mermaid architecture notes
├── examples/sample-vault/           # synthetic Markdown graph fixture
├── src/markdown_link_pagerank.py    # parser, graph builder, PageRank, CLI
└── tests/test_markdown_link_pagerank.py
```

## CLI

```bash
python3 src/markdown_link_pagerank.py --root <markdown-root> [options]
```

Options:

- `--output PATH` — write a Markdown report.
- `--json PATH` — write a JSON report.
- `--keywords "term-a,term-b"` — add a topic-biased PageRank section.
- `--limit N` — rows per report section. Default: `10`.
- `--damping FLOAT` — PageRank damping factor. Default: `0.85`.

If neither `--output` nor `--json` is provided, the CLI prints a compact Markdown report to stdout.

## Safety boundaries

- Reads Markdown text only.
- Skips generated and dependency folders such as `.git`, `.obsidian`, `node_modules`, `dist`, `build`, and `__pycache__`.
- Does not open network connections.
- Does not require API keys or runtime configuration files.
- Ships only synthetic example notes.

## Attribution

This repository is an original sanitized utility. It does not vendor third-party source code or datasets.

## License

MIT
