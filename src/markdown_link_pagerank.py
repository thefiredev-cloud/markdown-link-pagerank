#!/usr/bin/env python3
"""Build PageRank reports for local Markdown link graphs.

The tool understands Obsidian-style wikilinks and standard Markdown links that
point at ``.md`` files. It produces a deterministic ranking report without any
third-party runtime dependencies.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import unquote

WIKILINK_RE = re.compile(r"!?(?<!`)\[\[([^\]\n]+)\]\]")
MD_LINK_RE = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+?\.md(?:#[^)\n]+)?)\)")
GENERATED_REPORT_NAME = "MARKDOWN-PAGERANK-REPORT.md"
DEFAULT_SKIP_DIRS = {
    ".git",
    ".obsidian",
    ".trash",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    "coverage",
}


@dataclass(frozen=True)
class GraphReport:
    root: str
    generated_at: str
    node_count: int
    edge_count: int
    unresolved_count: int
    top_global: list[dict[str, float | str]]
    top_personalized: list[dict[str, float | str]]
    top_incoming: list[dict[str, int | str]]
    unresolved_targets: list[dict[str, int | str]]


def relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def read_ignore_patterns(root: Path) -> list[str]:
    """Read optional ignore patterns from ``.pagerankignore``."""
    ignore_file = root / ".pagerankignore"
    if not ignore_file.exists():
        return []
    patterns: list[str] = []
    for raw in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            patterns.append(line.rstrip("/"))
    return patterns


def is_ignored(relative: str, patterns: Sequence[str]) -> bool:
    parts = relative.split("/")
    if any(part in DEFAULT_SKIP_DIRS for part in parts):
        return True
    for pattern in patterns:
        pattern = pattern.strip("/")
        if not pattern:
            continue
        if relative == pattern or relative.startswith(pattern + "/"):
            return True
        if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(relative, pattern + "/**"):
            return True
        if "/" not in pattern and pattern in parts:
            return True
    return False


def iter_markdown(root: Path, patterns: Sequence[str] | None = None) -> list[Path]:
    patterns = list(patterns or read_ignore_patterns(root))
    files: list[Path] = []
    for path in root.rglob("*.md"):
        if path.is_file() and not is_ignored(relative_path(path, root), patterns):
            files.append(path)
    return sorted(files)


def clean_target(raw: str) -> str:
    target = raw.split("|", 1)[0]
    target = target.split("#", 1)[0]
    target = target.split("^", 1)[0]
    target = unquote(target).strip().replace("\\", "/")
    if target.endswith(".md"):
        target = target[:-3]
    return target.strip("/")


def extract_links(markdown: str) -> list[str]:
    links = [match.group(1) for match in WIKILINK_RE.finditer(markdown)]
    links.extend(match.group(1) for match in MD_LINK_RE.finditer(markdown))
    return links


def build_resolvers(files: Sequence[Path], root: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    exact: dict[str, str] = {}
    by_basename: dict[str, list[str]] = defaultdict(list)
    for path in files:
        rel = relative_path(path, root)
        without_ext = rel[:-3]
        exact[rel.lower()] = rel
        exact[without_ext.lower()] = rel
        by_basename[Path(without_ext).name.lower()].append(rel)
    return exact, by_basename


def resolve_target(raw: str, exact: dict[str, str], by_basename: dict[str, list[str]]) -> str | None:
    target = clean_target(raw)
    if not target:
        return None
    key = target.lower()
    if key in exact:
        return exact[key]
    if key + ".md" in exact:
        return exact[key + ".md"]
    if "/" not in key and len(by_basename.get(key, [])) == 1:
        return by_basename[key][0]
    return None


def build_graph(root: Path) -> tuple[dict[str, set[str]], Counter[str], Counter[str]]:
    files = iter_markdown(root)
    exact, by_basename = build_resolvers(files, root)
    adjacency: dict[str, set[str]] = {relative_path(path, root): set() for path in files}
    incoming: Counter[str] = Counter()
    unresolved: Counter[str] = Counter()

    for path in files:
        source = relative_path(path, root)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for raw in extract_links(text):
            target = resolve_target(raw, exact, by_basename)
            if target and target != source:
                adjacency[source].add(target)
                incoming[target] += 1
            else:
                cleaned = clean_target(raw)
                if cleaned:
                    unresolved[cleaned] += 1
    return adjacency, incoming, unresolved


def normalize(weights: dict[str, float], nodes: Sequence[str]) -> dict[str, float]:
    if not nodes:
        return {}
    cleaned = {node: max(0.0, float(weights.get(node, 0.0))) for node in nodes}
    total = sum(cleaned.values())
    if total <= 0:
        return {node: 1.0 / len(nodes) for node in nodes}
    return {node: cleaned[node] / total for node in nodes}


def pagerank(
    adjacency: dict[str, set[str]],
    damping: float = 0.85,
    personalization: dict[str, float] | None = None,
    max_iter: int = 100,
    tolerance: float = 1.0e-10,
) -> dict[str, float]:
    nodes = sorted(adjacency)
    if not nodes:
        return {}
    damping = min(0.99, max(0.01, damping))
    teleport = normalize(personalization or {}, nodes)
    rank = {node: 1.0 / len(nodes) for node in nodes}
    out_degree = {node: len(adjacency[node]) for node in nodes}

    for _ in range(max_iter):
        new_rank = {node: (1.0 - damping) * teleport[node] for node in nodes}
        dangling_mass = sum(rank[node] for node in nodes if out_degree[node] == 0)
        if dangling_mass:
            for node in nodes:
                new_rank[node] += damping * dangling_mass * teleport[node]
        for source, targets in adjacency.items():
            if not targets:
                continue
            share = damping * rank[source] / len(targets)
            for target in targets:
                new_rank[target] += share
        error = sum(abs(new_rank[node] - rank[node]) for node in nodes)
        rank = new_rank
        if error < len(nodes) * tolerance:
            break
    return rank


def keyword_personalization(nodes: Sequence[str], keywords: Sequence[str]) -> dict[str, float]:
    terms = [term.strip().lower() for term in keywords if term.strip()]
    weights: dict[str, float] = {}
    for node in nodes:
        haystack = node.lower().replace("_", " " ).replace("-", " " ).replace("/", " " )
        score = 0.05
        for term in terms:
            if term in haystack:
                score += 1.0
        weights[node] = score
    return normalize(weights, nodes)


def ranked_rows(rank: dict[str, float], limit: int) -> list[dict[str, float | str]]:
    rows = sorted(rank.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [{"path": path, "score": round(score, 10)} for path, score in rows]


def incoming_rows(incoming: Counter[str], limit: int) -> list[dict[str, int | str]]:
    return [
        {"path": path, "incoming_links": count}
        for path, count in sorted(incoming.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def unresolved_rows(unresolved: Counter[str], limit: int) -> list[dict[str, int | str]]:
    return [
        {"target": target, "count": count}
        for target, count in sorted(unresolved.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def build_report(root: Path, limit: int = 10, keywords: Sequence[str] = (), damping: float = 0.85) -> GraphReport:
    adjacency, incoming, unresolved = build_graph(root)
    nodes = sorted(adjacency)
    global_rank = pagerank(adjacency, damping=damping)
    personalized_rank = pagerank(
        adjacency,
        damping=damping,
        personalization=keyword_personalization(nodes, keywords) if keywords else None,
    )
    edge_count = sum(len(targets) for targets in adjacency.values())
    return GraphReport(
        root=str(root),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        node_count=len(nodes),
        edge_count=edge_count,
        unresolved_count=sum(unresolved.values()),
        top_global=ranked_rows(global_rank, limit),
        top_personalized=ranked_rows(personalized_rank, limit),
        top_incoming=incoming_rows(incoming, limit),
        unresolved_targets=unresolved_rows(unresolved, min(25, limit * 2)),
    )


def markdown_table(rows: Iterable[Mapping[str, object]], path_key: str, value_key: str, value_label: str) -> str:
    rows = list(rows)
    if not rows:
        return "_None._\n"
    out = [f"| Rank | {value_label} | Path |", "|---:|---:|---|"]
    for index, row in enumerate(rows, 1):
        out.append(f"| {index} | {row[value_key]} | `{row[path_key]}` |")
    return "\n".join(out) + "\n"


def to_markdown(report: GraphReport, keywords: Sequence[str] = ()) -> str:
    body = [
        "# Markdown Link PageRank Report",
        "",
        f"Generated: `{report.generated_at}`",
        f"Root: `{report.root}`",
        "",
        "## Scan stats",
        f"- Markdown nodes: **{report.node_count}**",
        f"- Resolved directed links: **{report.edge_count}**",
        f"- Unresolved link references: **{report.unresolved_count}**",
        "",
        "## Global PageRank",
        markdown_table(report.top_global, "path", "score", "Score"),
    ]
    if keywords:
        body.extend(
            [
                "## Keyword-personalized PageRank",
                f"Keywords: `{', '.join(keywords)}`",
                "",
                markdown_table(report.top_personalized, "path", "score", "Score"),
            ]
        )
    body.extend(
        [
            "## Most-linked notes",
            markdown_table(report.top_incoming, "path", "incoming_links", "Incoming links"),
            "## Unresolved link targets",
        ]
    )
    if report.unresolved_targets:
        body.extend(["| Count | Target |", "|---:|---|"])
        for row in report.unresolved_targets:
            body.append(f"| {row['count']} | `{row['target']}` |")
        body.append("")
    else:
        body.append("_None._\n")
    return "\n".join(body).rstrip() + "\n"


def parse_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank Markdown notes using PageRank over local links.")
    parser.add_argument("--root", type=Path, required=True, help="Markdown root to scan")
    parser.add_argument("--output", type=Path, help="Optional Markdown report path")
    parser.add_argument("--json", dest="json_path", type=Path, help="Optional JSON report path")
    parser.add_argument("--keywords", help="Comma-separated terms for personalized PageRank")
    parser.add_argument("--limit", type=int, default=10, help="Rows per ranking section")
    parser.add_argument("--damping", type=float, default=0.85, help="PageRank damping factor")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = args.root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"ERROR: root is not a directory: {root}", file=sys.stderr)
        return 2

    keywords = parse_keywords(args.keywords)
    report = build_report(root, max(1, args.limit), keywords, args.damping)
    markdown = to_markdown(report, keywords)

    if args.output:
        args.output.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output.expanduser().resolve().write_text(markdown, encoding="utf-8")
    if args.json_path:
        args.json_path.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.json_path.expanduser().resolve().write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
    if not args.output and not args.json_path:
        sys.stdout.write(markdown)
    elif args.output:
        print(args.output.expanduser().resolve())
    elif args.json_path:
        print(args.json_path.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
