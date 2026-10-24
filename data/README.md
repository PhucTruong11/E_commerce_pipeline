# Dữ liệu local

4 CSV trong bootstrap/ là đầu vào read-only, không commit. Bootstrap vào PostgreSQL source một lần; Python extract sang DuckDB Bronze, dbt xây Silver/Gold.

`warehouse/` và `serving/` là các vị trí host-dev cũ được giữ nguyên; runtime Docker hiện dùng named volumes riêng tại `/state/build`, `/state/releases`, `/state/artifacts`. Không nhầm các folder dữ liệu này với code dbt ở `../dbt/`. Chưa có pipeline data hoặc Gold release được sinh; môi trường chỉ có smoke artifacts.

CSV/checksum chỉ lưu baseline. Khi tạo OLTP changes, cần source backup hoặc change journal để tái lập lịch sử. Không dùng MinIO/S3 trong MVP. Xem [data flow](../docs/architecture.md), [CDC plan](../docs/cdc-plan.md).

Ignore rules tiếp tục loại CSV, DuckDB, artifacts và secrets; fixtures CI dùng dữ liệu tự tạo.
