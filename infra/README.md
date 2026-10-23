# Hạ tầng dự kiến

- docker/: Dockerfile cho runtime Python + psycopg + DuckDB + dbt Core/dbt-duckdb.
- postgres/init/: DDL nguồn của 4 bảng trong database project riêng.
- airflow/: cấu hình mount DAG vào platform có sẵn, không tạo control plane mới.

Hiện chỉ có scaffold. Máy này dùng lại PostgreSQL/Airflow chung theo [AGENTS](../AGENTS.md); chưa có Dockerfile/Compose/DDL mới, chưa provision/deploy. Không triển khai MinIO.

Khi cần chia sẻ, Compose standalone PostgreSQL + runtime sẽ thêm sau. Ngân sách và operator theo [Docker plan](../docs/docker-plan.md).
