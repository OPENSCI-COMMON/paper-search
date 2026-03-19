import pytest
from paper_search.service.search_service import PaperSearchService
from paper_search.models.paper import Paper, SearchResult, SnowballResult

def test_service_init():
    svc = PaperSearchService()
    assert len(svc.available_sources()) >= 10

def test_parse_sources_all():
    svc = PaperSearchService()
    assert svc._parse_sources("all") == svc.available_sources()

def test_parse_sources_specific():
    svc = PaperSearchService()
    result = svc._parse_sources("arxiv,pubmed,nonexistent")
    assert "arxiv" in result
    assert "pubmed" in result
    assert "nonexistent" not in result

def test_dedupe_papers():
    svc = PaperSearchService()
    papers = [
        Paper(paper_id="1", title="Paper A", doi="10.1/a"),
        Paper(paper_id="2", title="Paper B", doi="10.1/a"),  # same DOI
        Paper(paper_id="3", title="Paper C"),
    ]
    deduped = svc._dedupe_papers(papers)
    assert len(deduped) == 2

@pytest.mark.asyncio
async def test_search_empty_query():
    svc = PaperSearchService()
    result = await svc.search("")
    assert result.total == 0
    assert "query" in result.errors
