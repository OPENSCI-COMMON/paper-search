from paper_search.connectors.base import PaperConnector, ConnectorCapabilities
from paper_search.connectors.registry import ConnectorRegistry

def test_registry_discovers_connectors():
    reg = ConnectorRegistry()
    names = reg.all_names()
    assert "arxiv" in names
    assert "pubmed" in names
    assert len(names) >= 10

def test_registry_get():
    reg = ConnectorRegistry()
    arxiv = reg.get("arxiv")
    assert arxiv is not None
    assert isinstance(arxiv, PaperConnector)

def test_registry_contains():
    reg = ConnectorRegistry()
    assert "arxiv" in reg
    assert "nonexistent" not in reg
