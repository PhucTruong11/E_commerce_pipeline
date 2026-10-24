# E-commerce on the shared local data platform

Before setting up or changing Docker, Airflow, PostgreSQL or resource budgets, read:

- `D:/Dev/Project/airflow-platform/AGENTS.md`
- `D:/Dev/Project/airflow-platform/ARCHITECTURE.md`
- `D:/Dev/Project/airflow-platform/ONBOARDING.md`
- `D:/Dev/Project/airflow-platform/resources.json` (the operational registry, not the template in another repo)

Use the shared Airflow control plane and PostgreSQL service. For this machine, container DNS is `warehouse-laplaptech:5432` on `laplaptech-lab`; host connections use `127.0.0.1` and `WAREHOUSE_HOST_PORT` from the platform configuration. Never print the full platform `.env`.

E-commerce environment identity (provisioned 2026-10-24 on this machine): database `ecom_source_dev`, owner/bootstrap login `ecom_owner`, source extraction login `ecom_reader`, resource project/stage `ecom`/`refresh`. This supersedes the single-engine proposal `ecom_analytics_dev`; do not rename or migrate any existing database implicitly. The database, two non-admin roles and empty source/meta schemas are provisioned on this machine; bootstrap data, models and the DAG are not. Other machines must provision their own instance explicitly. See docs/docker.md. Create non-superuser project logins and validate the expected database/user before writing. Do not reuse the LaplapTech admin login, its runtime wrapper/config volume, or Airflow metadata database for project data.

Architecture: CSV bootstrap -> shared PostgreSQL source -> consistent Python snapshot extraction -> DuckDB Bronze -> dbt Core + dbt-duckdb Silver/Gold -> SQL insights. OLTP simulation and CDC are optional later phases; see docs/cdc-plan.md. MinIO/S3 is outside the MVP. Keep runtime/config/artifacts and DuckDB build/release volumes separate. The user approved initial repository cleanup: obsolete dlt/MinIO/Parquet samples and unused scaffold were removed from active paths into an ignored .local recovery folder. Keep the relevant CSV contract parser. Do not restore superseded samples as runtime entrypoints.

Register every Docker task in the operational `resources.json` and use the existing `BudgetDockerOperator` with pool `platform_memory`. Do not override its `pool`, `pool_slots`, `mem_limit` or `cpus`, or create an independent memory pool to bypass the platform budget. Keep single-writer protection with DAG concurrency and a runtime file lock on the shared project build volume held through extraction, dbt and publish. Manual writers must follow the same lock protocol. Close loader DuckDB connections before invoking dbt; serve only immutable Gold releases. CDC changes to shared PostgreSQL config/roles/slots require separate implementation and resource review.

The environment adds no persistent service. ecom/refresh is registered at 1024 MiB/1 CPU, dbt_threads=1 (2 shared pool slots). DuckDB starts at 512 MB/1 thread. BrewLite has three optional 512 MiB services (db/api/web); full BrewLite plus the shared Airflow stack exceeds the 8192 MiB host policy. Environment CLI uses a manual window with scheduler OFF and checks live limits through scripts/Invoke-Dev.ps1. Recheck the canonical policy and running services; do not silently shrink other projects' limits or change WSL settings.

Drain all platform runs/task containers before changing shared services, resource policy or DAG distribution. Preserve other projects' registrations, data, credentials, encryption keys and mounts. Manual runtime/CLI containers also consume the shared host budget and are not admitted by the Airflow pool; coordinate a drained/exclusive window or use the registered operator.

The user authorized deployment of the development environment on 2026-10-24. Docker runtime, separate PostgreSQL DB/roles, resource registration and environment checks are now in scope. Keep the project lean; implementing bootstrap/extraction, business models, DAG execution or CDC remains subsequent pipeline work. Never print passwords; secrets are separate local files, not env values baked into images.

Use `docs/architecture.md` for architecture/data flow, `docs/docker.md` for operations and `docs/plans/2026-10-24-ddl-bootstrap-extract.md` for the current implementation plan. dbt code lives in `dbt/models/bronze`, `silver`, `gold`; physical DuckDB schemas have those three names. Bronze sources are loaded by Python; dbt owns Silver/Gold transformations. Superseded plans and duplicate docs were removed from active paths with an ignored local recovery copy. The machine-specific paths above must be configured appropriately on another checkout.
