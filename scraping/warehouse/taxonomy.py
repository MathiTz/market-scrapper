"""The Cosmos category tree, loaded from the CSV the crawl produced.

Nothing here hardcodes a category: ``categorias.csv`` is the source of truth, so refreshing the
taxonomy is a file swap plus ``--rebuild-taxonomy``, not a code change.

Slugs are the join key, never the name: the crawl documents that names and slugs disagree
("Doces" lives at ``/balas``) and that two slugs carry UUIDs.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from warehouse import config

ROOT_SLUG = "alimentos-e-bebidas"


@dataclass(frozen=True)
class Node:
    slug: str
    name: str
    path: str
    parent_slug: Optional[str]
    depth: int
    is_leaf: bool

    @property
    def level(self) -> int:
        return self.depth


class Taxonomy:
    """The category tree, with the lookups classification needs."""

    def __init__(self, nodes: Iterable[Node]):
        self.nodes: Dict[str, Node] = {}
        for node in nodes:
            if node.slug in self.nodes:
                raise ValueError(f"duplicate category slug: {node.slug}")
            self.nodes[node.slug] = node
        self.children: Dict[str, List[Node]] = {}
        for node in self.nodes.values():
            if node.parent_slug:
                self.children.setdefault(node.parent_slug, []).append(node)
        for kids in self.children.values():
            kids.sort(key=lambda n: n.name)
        self.root = self.nodes.get(ROOT_SLUG)

    # -- construction ------------------------------------------------------

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Taxonomy":
        path = path or config.TAXONOMY_CSV
        if not Path(path).is_file():
            raise FileNotFoundError(f"taxonomy not found: {path}")
        nodes = []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                nodes.append(Node(
                    slug=row["slug"].strip(),
                    name=row["name"].strip(),
                    path=row["path"].strip(),
                    parent_slug=(row["parent_slug"] or "").strip() or None,
                    depth=int(row["depth"]),
                    is_leaf=row["is_leaf"].strip() == "1",
                ))
        return cls(nodes)

    # -- queries -----------------------------------------------------------

    @property
    def top_level(self) -> List[Node]:
        return self.children.get(ROOT_SLUG, [])

    @property
    def leaves(self) -> List[Node]:
        return sorted((n for n in self.nodes.values() if n.is_leaf), key=lambda n: n.path)

    def leaf_count(self) -> int:
        return len(self.leaves)

    def kids(self, slug: str) -> List[Node]:
        return self.children.get(slug, [])

    def get(self, slug: str) -> Optional[Node]:
        return self.nodes.get(slug)

    def subtree_leaves(self, slug: str) -> List[Node]:
        """Every leaf at or below ``slug``."""
        node = self.nodes.get(slug)
        if node is None:
            return []
        if node.is_leaf:
            return [node]
        found: List[Node] = []
        for child in self.kids(slug):
            found.extend(self.subtree_leaves(child.slug))
        return found

    def is_valid(self, slug: str) -> bool:
        return slug in self.nodes or slug == config.OUTSIDE_SLUG
