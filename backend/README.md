# FreightIQ Backend — Phase 2: Decision Engines (SIH26006)

**Intelligent Freight Forecasting and Charter Decision Support System for Bulk Cargo Procurement from Overseas to East Coast of India.**

---

## 1. Phase 2 Architecture & Service Responsibilities

```
backend/app/services/
├── feasibility_solver.py   # Hydrographic LOA, Beam, Draft, and DWT Berth Checker
├── scenario_engine.py      # Three-Way Payoff Simulator (Book Spot Now, Wait, Alt Vessel)
├── risk_engine.py          # Six-Dimension Risk Matrix Evaluator (0–100 Scores & Mitigations)
├── xai_engine.py           # Explainable Recommendation Synthesizer (WHEN / WHICH / WHY)
├── decision_engine.py      # Master Decision Orchestrator
└── csv_importer.py         # Multipart CSV Data Ingestion & Validation
```

### Service Responsibilities
1. **`feasibility_solver.py`**:
   - Compares nominated vessel dimensions against destination port limits stored in the database.
   - Audits DWT capacity, LOA, beam, permissible arrival draft (Chart Datum), air draft, cargo compatibility, and discharge throughput (TPD).
   - Generates exact parameter margins and status: `PASS`, `TIDAL_RESTRICTED`, or `REJECTED`.
2. **`scenario_engine.py`**:
   - Calculates exact financial payoffs for three commercial strategies:
     - `BOOK_SPOT_NOW`: `freight_cost = cargo_mt * spot_rate` (0 waiting penalty).
     - `WAIT_5_7_DAYS`: Incorporates daily demurrage holding penalty (`demurrage_rate * waiting_days`) against forecast rate. Transparently flags if forecast is unavailable.
     - `ALTERNATIVE_VESSEL`: Dynamically identifies a compliant alternative vessel from the fleet to overcome draft or parcel size bottlenecks.
3. **`risk_engine.py`**:
   - Evaluates six objective risk dimensions:
     1. *Freight Volatility*: Calculated from 30-day historical rates standard deviation and Coefficient of Variation.
     2. *Forecast Uncertainty*: Bounded by prediction intervals or flagged if ungenerated.
     3. *Port Congestion*: Derived from automated vs manual berth throughput.
     4. *Vessel Feasibility*: Penalizes tidal restrictions and structural violations.
     5. *Delay & Demurrage*: Demurrage rate sensitivity.
     6. *Data Quality*: Provenance tracking (Simulated Benchmark vs Verified Market Data).
4. **`xai_engine.py`**:
   - Mathematical rule engine (not an LLM chatbot) synthesizing traceable answers:
     - **WHEN?** Market entry timing window.
     - **WHICH VESSEL?** Nominated or alternative hull.
     - **IS IT FEASIBLE?** Hydrographic clearance status.
     - **WHAT ACTION?** Directive execution instruction.
     - **WHY?** Grounded evidence chain.
     - **KEY FACTORS**: Positive/negative influence attribution ledger.
5. **`decision_engine.py`**:
   - Master pipeline orchestrating Route ➔ Vessel ➔ Port ➔ Feasibility ➔ Forecast ➔ Scenarios ➔ Risk ➔ Recommendation into a single response object.

---

## 2. API Endpoints (Phase 1 & Phase 2)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Backend status, version, and database engine |
| `GET` | `/api/v1/routes` | List bulk shipping corridors |
| `GET` | `/api/v1/ports` | List discharge ports and berth dimensions |
| `GET` | `/api/v1/ports/{port_id}/constraints` | Hydrographic limits for specific port |
| `GET` | `/api/v1/vessels/presets` | Standard bulk carriers (Capesize to Handysize) |
| `GET` | `/api/v1/freight/history?route_id={id}&days=30` | Historical rate series with provenance |
| `GET` | `/api/v1/data-sources` | Registered data source metadata |
| `POST` | `/api/v1/freight/upload-csv` | Validate and ingest custom freight CSVs |
| `POST` | `/api/v1/feasibility/check` | Hydrographic vessel-berth clearance audit |
| `POST` | `/api/v1/scenarios/evaluate` | Three-way scenario financial payoff simulator |
| `POST` | `/api/v1/risk/evaluate` | Six-dimension risk matrix analysis |
| `POST` | `/api/v1/recommendation/explain` | Explainable AI recommendation generation |
| `POST` | `/api/v1/decision/analyze` | **Master Decision Pipeline** returning complete cockpit state |

---

## 3. Example Master Decision Request & Response

### Request: `POST /api/v1/decision/analyze`
```json
{
  "route_id": "australia-paradip",
  "vessel_id": "capesize",
  "cargo_quantity_mt": 140000,
  "cargo_type": "Coal"
}
```

### Response (Excerpt):
```json
{
  "route": {
    "id": "australia-paradip",
    "origin_port": "Newcastle",
    "destination_port_id": "paradip"
  },
  "feasibility": {
    "status": "PASS",
    "feasible": true,
    "checks": [
      {
        "parameter": "Length Overall (LOA)",
        "vessel_value": "292.0 m",
        "limit": "300.0 m max",
        "status": "PASS",
        "margin": 8.0,
        "reason": "Vessel LOA satisfies terminal pier limitations with 8.0m safety buffer."
      },
      {
        "parameter": "Permissible Arrival Draft",
        "vessel_value": "14.5 m",
        "limit": "14.5 m CD max",
        "status": "PASS",
        "margin": 0.0,
        "reason": "Vessel design draft satisfies navigation channel Chart Datum with 0.0m under-keel cushion."
      }
    ]
  },
  "scenarios": [
    {
      "scenario": "BOOK_SPOT_NOW",
      "feasible": true,
      "freight_rate": 19.85,
      "freight_cost": 2779000.0,
      "waiting_cost": 0.0,
      "total_cost": 2779000.0,
      "score": 90,
      "recommended": true
    },
    {
      "scenario": "WAIT_5_7_DAYS",
      "feasible": true,
      "freight_cost": 2779000.0,
      "waiting_cost": 157500.0,
      "total_cost": 2936500.0,
      "score": 45,
      "recommended": false
    },
    {
      "scenario": "ALTERNATIVE_VESSEL",
      "vessel_class": "Panamax",
      "freight_rate": 21.04,
      "total_cost": 2945600.0,
      "score": 68,
      "recommended": false
    }
  ],
  "risk": {
    "overall_risk_score": 34,
    "overall_risk_level": "LOW",
    "dimensions": [
      { "name": "Freight Volatility", "score": 25, "level": "LOW" },
      { "name": "Forecast Uncertainty", "score": 70, "level": "HIGH" },
      { "name": "Port Congestion", "score": 48, "level": "MEDIUM" },
      { "name": "Vessel Feasibility", "score": 15, "level": "LOW" },
      { "name": "Delay & Demurrage", "score": 28, "level": "LOW" },
      { "name": "Data Quality", "score": 45, "level": "MEDIUM" }
    ]
  },
  "recommendation": {
    "recommended_action": "BOOK_NOW",
    "when": "Prompt Fixture (Within 48 Hours)",
    "which_vessel": "Capesize",
    "feasibility": "FEASIBLE (PASS)",
    "what_action": "Execute spot charter fixture at observed rate ($19.85/MT).",
    "why": [
      "Schedule & Laycan Certainty: Immediate fixture eliminates laycan delay risk.",
      "Data Prudence: Forward forecast models are currently unavailable in database; waiting would incur holding cost without verified market discount evidence.",
      "Feasibility Status: Vessel conforms to Paradip Port terminal limits (PASS)."
    ],
    "key_factors": [
      {
        "factor": "Spot Market Certainty",
        "impact": "POSITIVE",
        "value": "$19.85/MT",
        "reason": "Locks in verified baseline rate and eliminates laycan penalties."
      },
      {
        "factor": "Holding Demurrage Cost",
        "impact": "NEGATIVE",
        "value": "$22,500/day",
        "reason": "Waiting incurs daily demurrage that outweighs unproven market dips."
      }
    ]
  },
  "data_provenance": "Simulated Benchmark Data (SIH26006 Research Prototype)"
}
```

---

## 4. Running Tests

Run the complete test suite using pytest:
```powershell
.\venv\Scripts\python.exe -m pytest tests -v
```

---

## 5. Starting the Backend Server

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Interactive OpenAPI documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
