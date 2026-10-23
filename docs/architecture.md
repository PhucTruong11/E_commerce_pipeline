# Kiến trúc: PostgreSQL → DuckDB → dbt → insight

> Quyết định cập nhật 2026-10-23 theo lựa chọn giữ PostgreSQL, DuckDB và dbt. Chỉ sửa thiết kế/tài liệu; chưa provision hoặc deploy.

![Data flow](diagrams/data-flow.svg)

## Vai trò từng thành phần

| Thành phần | Vai trò |
| --- | --- |
| 4 CSV gốc | Snapshot bootstrap, giữ read-only và checksum |
| PostgreSQL dùng chung | Database nguồn riêng; ban đầu chứa snapshot CSV, sau có thể luyện OLTP |
| Python + psycopg | Bootstrap bằng COPY; extract một snapshot nhất quán qua read-only transaction |
| DuckDB | Warehouse local, lưu Bronze và các lớp phân tích |
| dbt Core + dbt-duckdb | Silver staging/intermediate, Gold facts/marts, tests và docs |
| Docker runtime | Một image chạy bootstrap/extract/build; DuckDB là file trong volume, không thêm server |
| Airflow hiện có | Một DAG mỏng gọi runtime qua BudgetDockerOperator |
| SQL/report | Đầu ra chính: 15 câu hỏi và 3–5 phát hiện có bằng chứng |

Bỏ MinIO/S3 khỏi MVP. Chưa cần dlt, Kafka, Cosmos hoặc chatbot. Dùng Python để giữ ingestion nhỏ; thêm framework khi có nhu cầu cụ thể.

DuckDB bổ sung một bước sao chép dữ liệu so với dùng toàn PostgreSQL. Đổi lại, dự án học rõ ranh giới nguồn giao dịch và kho phân tích; dbt không chạy các aggregation trên PostgreSQL chung. Không tuyên bố stack này nhanh hơn ở mọi quy mô. Adapter dự kiến là [dbt-duckdb cho dbt Core](https://github.com/duckdb/dbt-duckdb); pin bộ phiên bản khi implementation.

## Ba chặng

1. **Snapshot và insight:** CSV bootstrap một lần vào PostgreSQL → full extract → DuckDB Bronze → dbt Silver/Gold → SQL/report.
2. **OLTP lab:** thêm các thao tác insert/update/delete có kiểm soát; kiểm thử đơn cũ sửa giá, khách/sản phẩm mới, xóa dòng. Full snapshot vẫn dùng được.
3. **CDC tùy chọn:** khi hai chặng đầu ổn, capture thay đổi nguồn và apply idempotently vào Bronze, rồi rebuild models chịu ảnh hưởng.

Không gọi polling theo updated_at là WAL-based CDC. CSV không đổi thì không tự sinh giao dịch hoặc change events. Có thể học CDC bằng nguồn mô phỏng, nhưng ghi rõ thay đổi là do simulator tạo. [CDC plan](cdc-plan.md).

## Database, schemas và quyền

PostgreSQL đề xuất: **ecom_source_dev**, schema e_commerce chứa 4 bảng nguồn; pipeline_meta giữ bootstrap inventory. Tên này thay đề xuất ecom_analytics_dev trước đó, chưa tạo hoặc rename database nào.

- ecom_owner: bootstrap/OLTP writer không superuser, chỉ database riêng.
- ecom_reader: extraction login chỉ đọc 4 bảng nguồn, không quyền ghi.
- Database limit đề xuất 8 connections; owner 4, reader 2. CDC cần role/permissions riêng, chưa cấp.
- PostgreSQL chung: warehouse-laplaptech:5432, network laplaptech-lab. Không dùng metadata Airflow hoặc credentials/config LaplapTech.
- Warehouse DuckDB: bronze (4 nguồn + extraction lineage), staging, intermediate, marts và pipeline_meta riêng. Staging/intermediate chủ yếu views, facts/marts tables.
- Reader báo cáo đọc file Gold-only được publish; không lấy tài khoản PG extractor làm tài khoản BI.

PG cần profile kiểu/PK/FK trước khi enforce DDL. Không biến dataset này thành hệ OLTP production chỉ bằng cách nạp CSV; nó là nguồn mô phỏng phục vụ học.

## Snapshot, writer và serving

Bootstrap không chạy lại để ghi đè giao dịch mỗi lần refresh. CSV mới cần explicit reset/new-baseline workflow; khi CDC hoạt động phải thiết kế cutover riêng.

Full extract đọc cả 4 bảng bằng **cùng connection và REPEATABLE READ READ ONLY transaction**. Mỗi lần tạo candidate DuckDB mới, COPY/insert theo batch; đối soát count/keys/sales/profit trước dbt. Không hứa transaction phân tán giữa PostgreSQL và DuckDB.

Một writer giữ runtime file lock trên volume chung từ extract tới publish; Airflow max_active_runs/max_active_tasks=1. Mọi CLI writers dùng cùng lock. Không giữ connection DuckDB Python mở khi dbt subprocess cần ghi cùng file.

Sau dbt build và reconciliation, xuất **Gold-only** sang file release mới, đóng writer, kiểm tra read-only và atomically thay active pointer trên cùng filesystem. Reader chọn một release cho cả request; không mở file build. Failed run không đổi pointer. Không chỉ copy nguyên build file vì Bronze/customer PII có thể đi theo.

Không có MinIO nghĩa là không có raw history ngoài warehouse được giữ. CSV backup chỉ tái lập baseline; thay đổi OLTP sau đó cần PG backup/change journal nếu muốn phục hồi lịch sử. Retention build/release và backup phải rõ, không hứa replay mọi thời điểm.
