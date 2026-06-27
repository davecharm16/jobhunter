from jobhunter.scan import ScanStore
from jobhunter.scan_store_pg import PostgresScanStore

def test_postgres_scan_store_is_a_scan_store():
    # structural check: all Protocol methods exist
    for m in ("get_settings", "update_settings", "known_urls", "record_scan",
              "list_candidates", "get_candidate", "set_candidate_status",
              "list_scans"):
        assert hasattr(PostgresScanStore, m)
