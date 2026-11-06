# Architecture

```mermaid
flowchart LR
    CSV[OPSD historical totals] --> Ingest[Interval normalization and validation]
    Ingest --> DAL[SQLAlchemy database access layer]
    DAL --> DB[(MySQL / offline SQLite)]
    Browser[Browser] --> Flask[Flask routes and HTML]
    Flask --> Service[Analysis service]
    Streamlit[Streamlit dashboard] --> Service
    Service --> DAL
    Replay[Historical replay] --> DAL
    Replay --> Pipeline[Filter + metrics transformer]
    Sample[Synthetic CSV iterator] --> Pipeline
```

The streaming and building class diagrams appear directly in the root README, as required for Homework 2. The iterator yields individual interval events; the pipeline is lazy. The full OPSD normalizer currently loads selected CSV columns with Pandas, so the prototype does not claim constant-memory ingestion of the entire raw dataset.

```mermaid
erDiagram
    BUILDING ||--o{ ZONE : contains
    ZONE ||--o{ METER : contains
    METER ||--o{ READING : records
    BUILDING {
        int id PK
        string name UK
        string type
        float floor_area_m2
    }
    ZONE {
        int id PK
        int building_id FK
        string name
    }
    METER {
        int id PK
        int zone_id FK
        string kind
        string unit
        string source
    }
    READING {
        int meter_id PK,FK
        string ts_utc PK
        float value
    }
```

Uniqueness: building name, `(building_id, zone name)`, `(zone_id, meter kind, source)`, and `(meter_id, UTC timestamp)`. Timestamps retain the existing canonical UTC text format (`YYYY-MM-DDTHH:MM:SSZ`), which sorts chronologically. Storage contains quarter-hour interval energy, never cumulative totals. Negative/non-finite input is rejected before persistence; foreign keys and nonnegative constraints protect writes. Repeat ingestion preserves existing readings at duplicate meter/timestamp keys.

Flask database selection uses a context-local override rather than modifying a process-wide setting, allowing independent app/test instances. Streamlit and CLI ingestion use `DATABASE_URL` from the environment or `.env`; an absent value uses the existing SQLite path. MySQL is the required Homework 3 backend. PostgreSQL remains outside this submission.

The demo has buildings, zones, and electricity meters. Portfolio/property ownership, additional energy carriers, learned anomaly detection, and live advisor integration remain capstone work.
