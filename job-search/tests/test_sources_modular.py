from career_job_search.opportunities.sources import (
    DiscoveryBatch,
    SourceDiscovery,
    SourceResult,
    discover_opportunities_with_results,
)

def test_sources_package_exports():
    assert DiscoveryBatch is not None
    assert SourceDiscovery is not None
    assert SourceResult is not None
    assert callable(discover_opportunities_with_results)
