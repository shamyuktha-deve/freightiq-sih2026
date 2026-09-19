import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def run_tests():
    print("=== STARTING FREIGHTIQ PHASE 1 API TESTS ===")
    
    # 1. Health check
    res = client.get("/api/v1/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    health = res.json()
    print("[PASS] /api/v1/health:", health["status"], "| DB:", health["database"])

    # 2. Routes
    res = client.get("/api/v1/routes")
    assert res.status_code == 200
    routes = res.json()
    assert len(routes) == 3
    print(f"[PASS] /api/v1/routes: Retrieved {len(routes)} routes ({[r['id'] for r in routes]})")

    # 3. Ports
    res = client.get("/api/v1/ports")
    assert res.status_code == 200
    ports = res.json()
    assert len(ports) == 3
    print(f"[PASS] /api/v1/ports: Retrieved {len(ports)} ports ({[p['name'] for p in ports]})")

    # 4. Port Constraints for Paradip
    res = client.get("/api/v1/ports/paradip/constraints")
    assert res.status_code == 200
    constraints = res.json()
    assert len(constraints) >= 1
    c = constraints[0]
    print(f"[PASS] /api/v1/ports/paradip/constraints: max_loa={c['max_loa']}m, max_draft={c['max_draft_cd']}m")

    # 5. Vessel Presets
    res = client.get("/api/v1/vessels/presets")
    assert res.status_code == 200
    vessels = res.json()
    assert len(vessels) == 5
    print(f"[PASS] /api/v1/vessels/presets: Retrieved {len(vessels)} vessel presets ({[v['vessel_class'] for v in vessels]})")

    # 6. Freight History
    res = client.get("/api/v1/freight/history?route_id=australia-paradip&days=30")
    assert res.status_code == 200
    history = res.json()
    assert history["total_records"] > 0
    assert history["is_simulated"] is True
    print(f"[PASS] /api/v1/freight/history: Retrieved {history['total_records']} records for australia-paradip (Source: {history['data_source']})")

    # 7. Data Sources
    res = client.get("/api/v1/data-sources")
    assert res.status_code == 200
    sources = res.json()
    assert len(sources) >= 3
    print(f"[PASS] /api/v1/data-sources: Retrieved {len(sources)} source provenance entries")

    # 8. CSV Upload Validation (Test Valid CSV)
    valid_csv_content = (
        "route_id,rate_date,spot_rate,currency,unit,data_source\n"
        "australia-paradip,2026-11-01,23.50,USD,MT,Custom Broker Import\n"
        "australia-vizag,2026-11-01,18.75,USD,MT,Custom Broker Import\n"
    )
    res = client.post(
        "/api/v1/freight/upload-csv",
        files={"file": ("test_valid.csv", valid_csv_content.encode("utf-8"), "text/csv")}
    )
    assert res.status_code == 200
    upload_res = res.json()
    assert upload_res["rows_inserted"] == 2
    assert upload_res["rows_rejected"] == 0
    print(f"[PASS] /api/v1/freight/upload-csv (Valid): Received {upload_res['rows_received']}, Inserted {upload_res['rows_inserted']}, Rejected {upload_res['rows_rejected']}")

    # 9. CSV Upload Validation (Test Invalid Records & Errors)
    invalid_csv_content = (
        "route_id,rate_date,spot_rate,currency,unit,data_source\n"
        "invalid-route,2026-11-02,20.00,USD,MT,Test\n"      # Invalid route
        "australia-paradip,not-a-date,20.00,USD,MT,Test\n"  # Invalid date format
        "australia-vizag,2026-11-02,-5.00,USD,MT,Test\n"    # Negative rate
        "australia-paradip,2026-11-01,23.50,USD,MT,Test\n"  # Duplicate of already existing date
    )
    res = client.post(
        "/api/v1/freight/upload-csv",
        files={"file": ("test_invalid.csv", invalid_csv_content.encode("utf-8"), "text/csv")}
    )
    assert res.status_code == 200
    inv_res = res.json()
    assert inv_res["rows_rejected"] == 4
    assert len(inv_res["validation_errors"]) == 4
    print(f"[PASS] /api/v1/freight/upload-csv (Invalid validation): Detected {len(inv_res['validation_errors'])} errors across 4 rejected rows (Zero silent failures!)")
    for err in inv_res["validation_errors"]:
        print(f"   -> Row {err['row_number']}: [{err['field']}] {err['error']}")

    print("\n=== ALL 9 API VERIFICATIONS PASSED 100%! ===")

if __name__ == "__main__":
    run_tests()
