# Operations · PostgreSQL source / DuckDB warehouse

> Runbook mục tiêu, chưa có CLI thực thi. [Data flow](data-flow.md), [Docker plan](docker-plan.md).

- Bootstrap CSV một lần; không reset nguồn ở mỗi refresh. Giữ source inventory và CSV backup.
- Full extract snapshot nhất quán sang candidate DuckDB mới, giữ file lock toàn run.
- Đóng connection loader trước dbt; full build/tests/reconcile rồi xuất Gold-only release.
- Serving chỉ đọc release immutable; pointer đổi sau pass. Build thất bại giữ release trước.
- Retry tạo candidate mới; không append snapshots vào facts. Không mở serving trực tiếp từ build file.
- Restore mất warehouse: nguồn hiện hành hoặc build snapshot được giữ; CSV chỉ phục hồi baseline, không bao gồm OLTP changes.
- Restore PostgreSQL phải scope database project; không reset cluster hoặc volume chung.
- Retention giữ active/previous releases và build snapshots cần audit; dọn orphan candidates sau khi xác nhận không có writer.
- Không commit DB/CSV/customer records, không log credentials. DuckDB read-only không tự là sandbox SQL an toàn cho LLM; Text-to-SQL chưa nằm trong MVP.
- Resource audit trước chạy; mọi CLI tuân thủ shared budget. DuckDB compute/spill nằm trong runtime/volume, PostgreSQL extraction dùng tài nguyên server chung.
- CDC chưa bật; khi thêm phải theo dõi WAL/journal storage theo [CDC plan](cdc-plan.md).
