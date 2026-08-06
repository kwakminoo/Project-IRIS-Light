from __future__ import annotations

from collections import Counter
from unittest import TestCase

from iris.knowledge.code_index import IrisCodeIndex


class CodeIndexTests(TestCase):
    def test_titles_unique_within_each_folder(self) -> None:
        """generate_code_docs.py writes one file per (folder, title) — collisions would silently overwrite."""
        files = IrisCodeIndex().list_files()
        by_folder: dict[str, Counter] = {}
        for cf in files:
            by_folder.setdefault(cf.folder, Counter())[cf.title] += 1
        dupes = {
            (folder, title): count
            for folder, counter in by_folder.items()
            for title, count in counter.items()
            if count > 1
        }
        self.assertEqual(dupes, {})

    def test_module_path_matches_real_import_form(self) -> None:
        files = IrisCodeIndex().list_files()
        wiki_graph = next(f for f in files if f.rel_path == "ui/knowledge/wiki_graph_view.py")
        self.assertEqual(wiki_graph.module, "iris.ui.knowledge.wiki_graph_view")
        self.assertIn("iris.knowledge.iris_wiki", wiki_graph.imports)
