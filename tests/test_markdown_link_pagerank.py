from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import markdown_link_pagerank as mlp


class MarkdownLinkPageRankTests(unittest.TestCase):
    def make_vault(self) -> tempfile.TemporaryDirectory[str]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "index.md").write_text(
            "# Index\n\n[[Alpha]]\n[[topics/Beta#Heading]]\n[Gamma](topics/gamma.md)\n[[Missing Note]]\n",
            encoding="utf-8",
        )
        (root / "Alpha.md").write_text("# Alpha\n\n[[index]]\n[[Beta|beta alias]]\n", encoding="utf-8")
        (root / "topics").mkdir()
        (root / "topics" / "Beta.md").write_text("# Beta\n\n[[index]]\n", encoding="utf-8")
        (root / "topics" / "gamma.md").write_text("# Gamma\n\n[[Alpha]]\n", encoding="utf-8")
        (root / ".obsidian").mkdir()
        (root / ".obsidian" / "workspace.md").write_text("# Ignored\n", encoding="utf-8")
        return temp

    def test_extract_links_supports_wikilinks_and_markdown_links(self) -> None:
        links = mlp.extract_links("[[Alpha|alias]] and [Beta](topics/Beta.md#Heading)")
        self.assertEqual(links, ["Alpha|alias", "topics/Beta.md#Heading"])

    def test_build_graph_resolves_exact_paths_and_unique_basenames(self) -> None:
        with self.make_vault() as temp:
            adjacency, incoming, unresolved = mlp.build_graph(Path(temp))
        self.assertIn("index.md", adjacency)
        self.assertEqual(adjacency["index.md"], {"Alpha.md", "topics/Beta.md", "topics/gamma.md"})
        self.assertIn("index.md", adjacency["Alpha.md"])
        self.assertIn("topics/Beta.md", adjacency["Alpha.md"])
        self.assertEqual(incoming["Alpha.md"], 2)
        self.assertEqual(unresolved["Missing Note"], 1)
        self.assertNotIn(".obsidian/workspace.md", adjacency)

    def test_pagerank_scores_sum_to_one(self) -> None:
        graph = {
            "index.md": {"Alpha.md", "Beta.md"},
            "Alpha.md": {"index.md"},
            "Beta.md": {"index.md"},
        }
        ranks = mlp.pagerank(graph)
        self.assertAlmostEqual(sum(ranks.values()), 1.0, places=8)
        self.assertGreater(ranks["index.md"], ranks["Alpha.md"])

    def test_build_report_has_global_and_keyword_sections(self) -> None:
        with self.make_vault() as temp:
            report = mlp.build_report(Path(temp), limit=3, keywords=["index"])
            markdown = mlp.to_markdown(report, ["index"])
        self.assertEqual(report.node_count, 4)
        self.assertGreaterEqual(report.edge_count, 6)
        self.assertIn("Keyword-personalized PageRank", markdown)
        self.assertIn("Missing Note", markdown)

    def test_cli_writes_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            output = Path(output_dir) / "report.md"
            json_output = Path(output_dir) / "report.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "src" / "markdown_link_pagerank.py"),
                    "--root",
                    str(ROOT / "examples" / "sample-vault"),
                    "--output",
                    str(output),
                    "--json",
                    str(json_output),
                    "--keywords",
                    "architecture,decision,index",
                    "--limit",
                    "5",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertTrue(output.exists())
            data = json.loads(json_output.read_text(encoding="utf-8"))
            self.assertGreaterEqual(data["node_count"], 5)
            self.assertGreaterEqual(data["edge_count"], 8)
            self.assertTrue(data["top_global"])


if __name__ == "__main__":
    unittest.main()
