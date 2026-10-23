# Dữ liệu local

4 CSV trong bootstrap/ là đầu vào read-only, không commit. Bootstrap vào PostgreSQL source một lần; Python extract sang DuckDB Bronze, dbt xây Silver/Gold.

warehouse/ là vị trí host dev dự kiến cho candidate/build DuckDB và lineage; Docker dùng volume riêng mount nhất quán vào runtime. serving/ giữ Gold-only immutable releases và active pointer khi triển khai. Hiện chưa có pipeline artifacts được sinh.

CSV/checksum chỉ lưu baseline. Khi tạo OLTP changes, cần source backup hoặc change journal để tái lập lịch sử. Không dùng MinIO/S3 trong MVP. Xem [data flow](../docs/data-flow.md), [CDC plan](../docs/cdc-plan.md).

Ignore rules tiếp tục loại CSV, DuckDB, artifacts và secrets; fixtures CI dùng dữ liệu tự tạo.
