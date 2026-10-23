# E-commerce on the shared local data platform

Before setting up or changing Docker, Airflow, PostgreSQL or resource budgets, read:

- `D:/Dev/Project/airflow-platform/AGENTS.md`
- `D:/Dev/Project/laplaptech_pipeline/docs/guides/resources.md`
- `D:/Dev/Project/airflow-platform/resources.json` (the operational registry, not the template in another repo)

Use the shared Airflow control plane and PostgreSQL service. For this machine, container DNS is `warehouse-laplaptech:5432` on `laplaptech-lab`; host connections use `127.0.0.1` and `WAREHOUSE_HOST_PORT` from the platform configuration. Never print the full platform `.env`.

Planned e-commerce identity (revised 2026-10-23): database `ecom_source_dev`, owner/bootstrap login `ecom_owner`, source extraction login `ecom_reader`, resource project/stage `ecom`/`refresh`. This supersedes the single-engine proposal `ecom_analytics_dev`; do not rename or migrate any existing database implicitly. These are proposed identifiers, not evidence that they have been provisioned. Create non-superuser project logins and validate the expected database/user before writing. Do not reuse the LaplapTech admin login, its runtime wrapper/config volume, or Airflow metadata database for project data.

Architecture: CSV bootstrap -> shared PostgreSQL source -> consistent Python snapshot extraction -> DuckDB Bronze -> dbt Core + dbt-duckdb Silver/Gold -> SQL insights. OLTP simulation and CDC are optional later phases; see docs/cdc-plan.md. MinIO/S3 is outside the MVP. Keep runtime/config/artifacts and DuckDB build/release volumes separate. The user approved initial repository cleanup: obsolete dlt/MinIO/Parquet samples and unused scaffold were removed from active paths into an ignored .local recovery folder. Keep the relevant CSV contract parser. Do not restore superseded samples as runtime entrypoints.

Register every Docker task in the operational `resources.json` and use the existing `BudgetDockerOperator` with pool `platform_memory`. Do not override its `pool`, `pool_slots`, `mem_limit` or `cpus`, or create an independent memory pool to bypass the platform budget. Keep single-writer protection with DAG concurrency and a runtime file lock on the shared project build volume held through extraction, dbt and publish. Manual writers must follow the same lock protocol. Close loader DuckDB connections before invoking dbt; serve only immutable Gold releases. CDC changes to shared PostgreSQL config/roles/slots require separate implementation and resource review.

The new MVP adds no persistent service on this machine. If a dashboard or another service is added later, register its idle memory/CPU. The LaplapTech dashboard and the 512 MiB BrewLite database are now optional services in the shared registry. With BrewLite running and the dashboard stopped, the effective budget is 7936/8192 MiB; a new 512 MiB MinIO service does not fit concurrently. Recheck the live policy and running services before deployment; do not silently shrink other projects' limits or change WSL settings.

Drain all platform runs/task containers before changing shared services, resource policy or DAG distribution. Preserve other projects' registrations, data, credentials, encryption keys and mounts. Manual runtime/CLI containers also consume the shared host budget and are not admitted by the Airflow pool; coordinate a drained/exclusive window or use the registered operator.

Current approved scope includes plans/docs and the initial project-local folder scaffold/cleanup requested by the user. The project is for learning technologies and commercial analytics; keep the initial scaffold lean. Actual DB/role creation, platform registry edits, deployment, service restarts and DAG execution are separate implementation work. Read-only checks and project-local documentation changes may proceed within that scope.

See `docs/architecture.md`, `docs/ingestion-plan.md` and `docs/docker-plan.md` for the active plan. `docs/platform-check-2026-10-22.md` is historical audit evidence; superseded plans are no longer part of active documentation. The machine-specific paths above must be configured appropriately on another checkout.
