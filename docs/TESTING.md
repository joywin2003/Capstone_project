# Verification

Use the project virtual environment. Default pytest selection excludes tests marked `integration`:

```bash
python -m pytest -q
python -m backend.streaming.demo
python -m pip check
```

For MySQL, use a **dedicated disposable database whose name starts with `energy_homework_test`**. The integration fixture drops/recreates the application's tables in that database. Never point it at a demonstration or real database. Create this database and grant your test user access using your local MySQL administrator.

```bash
export TEST_DATABASE_URL='mysql+pymysql://test_user:test_password@127.0.0.1:3307/energy_homework_test?charset=utf8mb4'
python -m pytest -q -m integration
```

Selecting integration tests without a valid dedicated URL fails visibly. Integration tests check persistence through a new connection, duplicate-ingestion idempotency, rollback after a foreign-key failure, and Flask output from actual MySQL. SQLite results do not demonstrate MySQL compatibility.

Automated results and the final Homework 4 test inventory are recorded once that branch is verified. The video and personal student details are separate submission tasks.

## Homework 3 verified results (6 November 2026)

- Python 3.14.7; Flask 3.1.3; SQLAlchemy 2.1.8; PyMySQL 1.2.3; MySQL Community Server 8.4.11.
- Stream tests: **11 passed** (including CSV/configuration boundary checks).
- Real MySQL integration tests: **4 passed** (persistence, idempotency, rollback, Flask KPI/HTML output).
- Temporary MySQL ran locally on port 33317 for verification. The documented Compose setup uses port 3307; Docker Compose itself was not run because this machine's Docker daemon was unavailable.
- Offline SQLite smoke check: HTML table, building list, latest reading, and known-period KPIs all returned 200 with expected data.
