"""Core search orchestration service."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ..connectors.registry import ConnectorRegistry
from ..connectors.base import PaperConnector
from ..models.paper import Paper, SearchResult, SnowballResult

logger = logging.getLogger(__name__)


class PaperSearchService:
    def __init__(self, registry: Optional[ConnectorRegistry] = None):
        self.registry = registry or ConnectorRegistry()

    def available_sources(self) -> List[str]:
        return self.registry.all_names()

    async def search(
        self,
        query: str,
        sources: str = "all",
        max_results_per_source: int = 5,
        year: Optional[str] = None,
    ) -> SearchResult:
        if not query or not query.strip():
            return SearchResult(
                query=query or "",
                sources_requested=sources,
                errors={"query": "Query string is empty."},
            )

        selected = self._parse_sources(sources)
        if not selected:
            return SearchResult(
                query=query,
                sources_requested=sources,
                errors={"sources": "No valid sources selected."},
            )

        task_map: Dict[str, asyncio.Task] = {}
        for name in selected:
            connector = self.registry.get(name)
            if connector is None:
                continue
            kwargs: Dict[str, Any] = {}
            if year and name == "semantic":
                kwargs["year"] = year
            task_map[name] = asyncio.ensure_future(
                self._async_search(connector, query, max_results_per_source, **kwargs)
            )

        source_names = list(task_map.keys())
        outputs = await asyncio.gather(*task_map.values(), return_exceptions=True)

        source_results: Dict[str, int] = {}
        errors: Dict[str, str] = {}
        merged: List[Paper] = []

        for name, output in zip(source_names, outputs):
            if isinstance(output, Exception):
                errors[name] = str(output)
                source_results[name] = 0
                continue
            source_results[name] = len(output)
            for paper in output:
                if not paper.source:
                    paper.source = name
                merged.append(paper)

        deduped = self._dedupe_papers(merged)

        return SearchResult(
            query=query,
            sources_requested=sources,
            sources_used=source_names,
            source_results=source_results,
            errors=errors,
            papers=deduped,
            total=len(deduped),
            raw_total=len(merged),
        )

    async def snowball(
        self,
        paper_id: str,
        direction: str = "both",
        max_results_per_direction: int = 20,
        depth: int = 1,
    ) -> SnowballResult:
        depth = min(max(depth, 1), 3)
        semantic = self.registry.get("semantic")
        if semantic is None:
            return SnowballResult(
                seed_paper_id=paper_id,
                direction=direction,
                depth=depth,
                errors=["Semantic Scholar connector not available"],
            )

        all_papers: List[Paper] = []
        visited: set[str] = set()
        current_ids = [paper_id]
        layer_errors: List[str] = []

        for layer in range(depth):
            next_ids: List[str] = []
            for idx, pid in enumerate(current_ids):
                if pid in visited:
                    continue
                visited.add(pid)

                if layer > 0 or idx > 0:
                    await asyncio.sleep(1.0)

                refs: List[Paper] = []
                cites: List[Paper] = []

                if direction in ("backward", "both"):
                    try:
                        refs = await asyncio.to_thread(
                            semantic.get_references, pid, max_results_per_direction
                        )
                    except Exception as exc:
                        layer_errors.append(f"layer{layer}:refs:{pid}:{exc}")

                if direction in ("forward", "both"):
                    if direction == "both":
                        await asyncio.sleep(1.0)
                    try:
                        cites = await asyncio.to_thread(
                            semantic.get_citations, pid, max_results_per_direction
                        )
                    except Exception as exc:
                        layer_errors.append(f"layer{layer}:cites:{pid}:{exc}")

                for p in refs + cites:
                    all_papers.append(p)
                    if p.paper_id and p.paper_id not in visited:
                        next_ids.append(p.paper_id)

            current_ids = next_ids
            if not current_ids:
                break

        deduped = self._dedupe_papers(all_papers)
        return SnowballResult(
            seed_paper_id=paper_id,
            direction=direction,
            depth=depth,
            total=len(deduped),
            raw_total=len(all_papers),
            papers=deduped,
            errors=layer_errors,
        )

    async def recommend(
        self,
        paper_id: str,
        max_results: int = 10,
    ) -> SearchResult:
        """Find similar papers using Semantic Scholar embedding-based recommendations.

        Args:
            paper_id: Semantic Scholar paper ID, or DOI:<doi>, ARXIV:<id>, etc.
            max_results: Maximum number of recommendations.
        """
        semantic = self.registry.get("semantic")
        if semantic is None:
            return SearchResult(
                query=f"recommend:{paper_id}",
                sources_requested="semantic",
                errors={"semantic": "Semantic Scholar connector not available"},
            )

        try:
            papers = await asyncio.to_thread(
                semantic.get_recommendations, paper_id, max_results
            )
        except Exception as exc:
            return SearchResult(
                query=f"recommend:{paper_id}",
                sources_requested="semantic",
                errors={"semantic": str(exc)},
            )

        deduped = self._dedupe_papers(papers)
        return SearchResult(
            query=f"recommend:{paper_id}",
            sources_requested="semantic",
            sources_used=["semantic"],
            source_results={"semantic": len(deduped)},
            papers=deduped,
            total=len(deduped),
            raw_total=len(papers),
        )

    @staticmethod
    async def _async_search(
        connector: PaperConnector,
        query: str,
        max_results: int,
        **kwargs,
    ) -> List[Paper]:
        papers = await asyncio.to_thread(
            connector.search, query, max_results=max_results, **kwargs
        )
        return papers or []

    def _parse_sources(self, sources: str) -> List[str]:
        if not sources or sources.strip().lower() == "all":
            return self.available_sources()
        normalized = [s.strip().lower() for s in sources.split(",") if s.strip()]
        return [s for s in normalized if s in self.registry]

    @staticmethod
    def _dedupe_papers(papers: List[Paper]) -> List[Paper]:
        deduped: List[Paper] = []
        seen: set[str] = set()
        for p in papers:
            key = PaperSearchService._paper_key(p)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(p)
        return deduped

    @staticmethod
    def _paper_key(paper: Paper) -> str:
        doi = (paper.doi or "").strip().lower()
        if doi:
            return f"doi:{doi}"
        title = (paper.title or "").strip().lower()
        authors = "; ".join(paper.authors).strip().lower() if paper.authors else ""
        if title:
            return f"title:{title}|authors:{authors}"
        return f"id:{(paper.paper_id or '').strip().lower()}"
