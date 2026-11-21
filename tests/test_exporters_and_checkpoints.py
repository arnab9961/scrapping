import pytest
import json
from services.checkpoint import save_checkpoint, get_checkpoint, clear_checkpoint
from services.exporter import stream_csv_export, stream_json_export, generate_excel_export
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_checkpoint_persistence_lifecycle():
    job_id = "test_job_12345"
    state = {
        "current_query_idx": 2,
        "queries": ["hotels in dhaka", "resorts in kuakata"],
        "processed_urls": ["https://example1.com", "https://example2.com"],
        "qualified_count": 14
    }
    # Save checkpoint
    save_checkpoint(job_id, state)

    # Retrieve checkpoint
    retrieved = get_checkpoint(job_id)
    assert retrieved is not None
    assert retrieved["current_query_idx"] == 2
    assert retrieved["qualified_count"] == 14
    assert len(retrieved["processed_urls"]) == 2

    # Clear checkpoint
    clear_checkpoint(job_id)
    cleared = get_checkpoint(job_id)
    assert cleared is None

def test_export_formats_endpoints():
    # CSV export
    res_csv = client.get("/api/export/csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "Business Name" in res_csv.text

    # JSON array export
    res_json = client.get("/api/export/json")
    assert res_json.status_code == 200
    assert "application/json" in res_json.headers["content-type"]
    data = json.loads(res_json.text)
    assert isinstance(data, list)

    # JSONL export
    res_jsonl = client.get("/api/export/jsonl")
    assert res_jsonl.status_code == 200
    assert "x-ndjson" in res_jsonl.headers["content-type"]

    # Excel export
    res_excel = client.get("/api/export/excel")
    assert res_excel.status_code == 200
    assert "spreadsheetml" in res_excel.headers["content-type"]
    assert len(res_excel.content) > 1000 # Valid zip/xlsx payload
