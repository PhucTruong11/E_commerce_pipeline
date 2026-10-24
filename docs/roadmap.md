# Roadmap học tech và commercial analytics

> Cập nhật 2026-10-24. Checklist tách bằng chứng đã có và việc chưa làm; không phải lệnh triển khai.

Buổi hiện tại: [Bootstrap và snapshot extraction](plans/2026-10-24-bootstrap-extract.md). Hai loader đã viết, build, fixture-test và chạy dữ liệu thật: đủ 100.889 dòng PostgreSQL → DuckDB Bronze; retry bootstrap skipped. Không cần bước DDL riêng.

## 0. Initial scaffold

- [x] Tạo thư mục config, infra Docker/Airflow, ingestion, dbt, orchestration, tests và commercial reports.
- [x] Giữ 4 CSV, parser và tài liệu hiện hành; đưa mẫu/scaffold không dùng khỏi source vào vùng khôi phục local.
- [x] Cập nhật tree, trạng thái implementation và ignore rules hiện có.
- [x] Thiết lập môi trường Docker dev, DB/roles/schema rỗng và kiểm tra quyền/kết nối.
- [x] Viết bootstrap/extractor và nối CLI Docker.

## 1. Input và contract

- [x] Có đủ 4 CSV local; inventory 100.889 dòng và khoảng 8,76 MiB.
- [x] Đã kiểm tra headers, số cột và khóa ứng viên không rỗng/trùng.
- [x] Đổi kiến trúc sang CSV → PostgreSQL source → DuckDB Bronze → dbt-duckdb → marts.
- [x] Profile kiểu, precision, ISO date parsing, null và orphan keys; giữ tất cả sales.
- [ ] Kiểm thêm date range, quantity/discount nghiệp vụ, tiền tệ và sales/profit semantics.
- [ ] Xác nhận order key và header consistency; xác nhận product-code identity.

**Đạt khi:** có data contract và báo cáo profiling không chứa PII. Vấn đề semantic chưa xác minh phải ghi rõ, không chọn giá trị đoán làm chuẩn.

## 2. Source, Bronze và runtime nhỏ

- [x] Tạo runtime Docker Python + psycopg + dbt-duckdb, dependencies được ghim.
- [x] Cấp database/users/schema riêng và identity guard; [runbook](docker.md).
- [x] Sinh định nghĩa bốn bảng nguồn từ typed contract trong bootstrap; không duy trì DDL rời.
- [x] Implement bootstrap COPY/ledger và PG snapshot → DuckDB candidate; kiểm chứng trên fixture.
- [x] Chạy bootstrap/extract dữ liệu thật; đối soát đủ 100.889 dòng, hash/nulls/totals và lineage đạt.
- [x] Fixture: rollback, retry, source thay đổi đồng thời, writer lock, quyền reader, failed candidate cleanup.
- [ ] Gold publish và thử publish failure.
- [x] Smoke kết nối bằng owner/reader riêng, không dùng admin runtime; DuckDB và dbt debug.

**Đạt khi:** bootstrap/extract đúng snapshot, không duplicate, failed build giữ Gold trước. Không thêm MinIO; OLTP/CDC là chặng sau.

## 3. Facts và insight đầu tiên

- [ ] 4 staging models và tests cần thiết.
- [ ] `fct_order_lines`, `fct_orders`, dimensions chỉ khi cần dùng lại.
- [ ] Đối soát row count, sales, profit và order roll-up.
- [ ] `mart_monthly_performance`, `mart_product_performance`, `mart_customer_rfm`.
- [ ] SQL Q01–Q07, Q10–Q14; bắt đầu từ total, segment, discount, margin và loss orders.
- [ ] Q08 sau khi chốt VIP/risk rule; Q09/Q15 sau kiểm tra basket population và product identity.

**Đạt khi:** trả lời 15 câu hỏi hoặc ghi rõ câu nào chưa đủ điều kiện dữ liệu. Không ép tạo insight khi dữ liệu không hỗ trợ.

## 4. Báo cáo kinh doanh

- [ ] Báo cáo 3–5 phát hiện có số liệu, query, kỳ và analysis_run_id.
- [ ] Mỗi phát hiện có tác động, hành động đề xuất và điểm cần kiểm chứng.
- [ ] Phân biệt tương quan với nguyên nhân; rà RFM/churn-risk và basket minimum support.
- [ ] Người khác chạy lại cùng source snapshot/code/config tạo cùng metric; CSV chỉ tương đương khi nguồn chưa có OLTP changes.

**Đạt khi:** giải thích được quyết định kinh doanh mà pipeline hỗ trợ; chưa cần chatbot/dashboard.

## 5. Airflow và chia sẻ repo

- [x] Đăng ký ecom/refresh 1024 MiB/1 CPU trong registry sau khi xác nhận platform đã drain; chưa deploy DAG.
- [ ] DAG `ecom_analytics_refresh`, một task runtime, concurrency 1, dùng BudgetDockerOperator.
- [ ] Test lock, retry, timeout, dbt fail và resource limits.
- [ ] CLI Compose standalone gồm PostgreSQL + runtime cho người chưa có platform.
- [ ] README quickstart đã thử với synthetic fixtures; CI chạy checks có giá trị.
- [ ] Dashboard nếu cần; đăng ký ngân sách idle trước khi bật.

Airflow chưa cần lịch cố định cho CSV tĩnh. Với máy hiện tại dùng service chung; standalone dành người clone, không dựng thêm trên máy này.

## 6. OLTP và CDC tùy chọn

Sau khi insight ổn: thêm controlled insert/update/delete trong PostgreSQL; sau đó PoC CDC theo [CDC plan](cdc-plan.md), kiểm snapshot-to-WAL boundary, delete, dedup/checkpoint và retained WAL. Chưa chọn connector hoặc sửa shared PostgreSQL config.
