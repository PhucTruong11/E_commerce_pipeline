# Architecture

> Thiết kế mục tiêu, chưa phải mô tả hệ thống đã triển khai. Ngày thiết kế: 2026-10-19.

## Bối cảnh và mục tiêu

Xóm E-Com có dữ liệu bán hàng, khách hàng, sản phẩm và địa lý. Mục tiêu học tập là thiết kế một ELT pipeline có thể chạy lại, xử lý thay đổi và phục hồi từ raw, đồng thời cung cấp dữ liệu có grain rõ ràng cho 15 câu hỏi nghiệp vụ.

Quy mô dữ liệu hiện tại không đòi hỏi distributed compute. MinIO và Postgres giả lập được thêm để luyện ranh giới source/storage/compute và thử các tình huống lỗi. Đây là lựa chọn theo mục tiêu học tập, không phải yêu cầu hiệu năng của dataset.

## Kiến trúc tổng thể

![Data flow](diagrams/data-flow.svg)

| Thành phần | Trách nhiệm | Không chịu trách nhiệm |
| --- | --- | --- |
| Bootstrap / simulator | Nhập snapshot vào Postgres; sinh insert/update có kiểm soát | Suy diễn rằng dữ liệu giả lập là giao dịch thực |
| PostgreSQL source | Lưu dữ liệu nguồn mô phỏng; cấp quyền đọc riêng cho ingestion | Phục vụ BI hoặc chạy transformations nặng |
| dlt ingestion | Extract, chuẩn hóa kiểu để ghi Parquet, ghi metadata batch | Tính RFM hoặc business KPIs |
| MinIO raw | Archive payload nguồn theo batch; manifest và schema | Là trạng thái current-state đã merge |
| DuckDB Bronze loader | Chỉ đọc batch committed; apply snapshot/upsert có đối soát | Đọc lại Postgres khi dbt cần retry |
| dbt | Silver, Gold, docs và data tests | Extract nguồn hay tự publish release |
| Airflow | DAG dependencies, retry, giới hạn writer, quality gate, publish | Chứa toàn bộ business logic hoặc thay thế transaction database |
| Serving | Streamlit và API Text-to-SQL đọc release đã publish | Mở file build đang được dbt ghi |
| GitHub Actions | Kiểm tra PR với fixtures giả lập | Là scheduler cho pipeline thay Airflow |

Raw ở đây bảo toàn **giá trị nguồn cùng schema/metadata** trong Parquet, không cam kết giữ nguyên byte của database export. Phải kiểm tra precision/scale của decimal và round-trip kiểu ngày khi triển khai.

## Các quyết định thiết kế

| Quyết định | Lý do | Hệ quả |
| --- | --- | --- |
| Hai chế độ: Airflow có sẵn / standalone Compose | Tận dụng môi trường hiện tại, vẫn chia sẻ repo tự chạy được | Dùng chung runtime và DAG; cấu hình network/storage riêng |
| Postgres giả lập từ snapshot | Chủ động tạo update và lỗi | Gắn nhãn nguồn mô phỏng; không thay đổi schema công bố của Xóm Data trong tài liệu |
| Batch incremental, chưa log CDC | Đủ cho mục tiêu học tập giai đoạn đầu | Cần `updated_at` đáng tin; hard delete nằm ngoài MVP |
| Raw Parquet bất biến | Replay và audit | Upsert thực hiện ở Bronze, không ghi đè lịch sử raw |
| DuckDB build + releases bất biến | Tách writer khỏi người đọc | Serving cần đổi release bằng cách đóng/mở kết nối |
| dbt full rebuild ban đầu | Đơn giản hóa tính đúng khi sửa đơn cũ | Incremental dbt là tối ưu sau khi có bằng chứng cần thiết |
| Streamlit trước, Gemini sau | Hoàn tất dữ liệu và metric trước lớp AI | Dashboard và Text-to-SQL cùng dùng contract Gold |
| Một orchestrator: Apache Airflow | Tận dụng Airflow đã có trên máy | Ghim phiên bản theo môi trường thực tế; không đổi/nâng cấp Airflow hiện có tự động |
| DAG mỏng + project runtime | Giữ code pipeline độc lập với orchestrator | Copy DAG cần kèm runtime đã cài và cấu hình; dbt CLI trước, Cosmos tùy chọn sau |

## Storage và ranh giới lớp

- **Raw / MinIO:** batch archive, mỗi bảng có manifest và schema; không chứa business dedup âm thầm.
- **Bronze / DuckDB:** dữ liệu nguồn đã apply theo snapshot hoặc incremental; metadata và ledger phục vụ audit.
- **Silver / DuckDB:** kiểu dữ liệu chuẩn, khóa đã xác nhận, join được kiểm soát, order roll-up.
- **Gold / DuckDB:** dimensions, facts và marts có mô tả metric, grain, thời gian và giới hạn sử dụng.
- **Serving release:** file database riêng chỉ chứa Gold được duyệt và metadata release, không phát hành toàn bộ raw/customer PII.

MinIO + DuckDB là thiết kế lake-backed analytics theo hướng lakehouse. MVP chưa có transactional table format như Iceberg/Delta, catalog tập trung hoặc ACID transaction trên tập Parquet. Lake và warehouse không bắt buộc luôn đứng nối tiếp trong mọi hệ thống.

## Concurrency và publish

Airflow dùng DAG `max_active_runs=1`, pool writer có một slot và runtime file lock cho cùng file DuckDB, bao gồm manual runs và backfills. Pool chỉ bảo vệ tasks thực sự được gán vào pool; script ngoài Airflow vẫn phải tuân thủ file lock. MVP giữ load Bronze, dbt build, gate và publish trong một task `build_and_publish` để giữ lock suốt vòng build, tránh các run xen kẽ giữa load và publish. dbt có thể quản lý concurrency bên trong process/connection của nó theo khả năng adapter.

Với standalone demo, ưu tiên single-host LocalExecutor và shared volume có semantics khóa file được kiểm tra. Nếu Airflow có sẵn dùng Celery/Kubernetes, cần bố trí worker/storage tương thích hoặc chỉ định một worker chuyên dụng; không giả định file local của task trước tự xuất hiện ở task sau. Chi tiết hai chế độ và giới hạn nằm trong [Airflow & Docker](airflow-docker.md).

Sau khi quality gate đạt, publisher đóng kết nối writer, tạo file serving theo `release_id`, kiểm tra read-only rồi cập nhật pointer release bằng atomic replace trên cùng filesystem. Không copy database đang có writer hoạt động. Không thay thế file `.duckdb` mà dashboard đang mở trên Windows; người đọc đóng kết nối cũ và mở đường dẫn phiên bản mới. Giữ release trước để rollback.

Chi tiết transaction và recovery nằm trong [data flow](data-flow.md) và [operations](operations.md).

## An toàn dữ liệu và Text-to-SQL

- `.env`/secret store giữ credentials; repository chỉ chứa `.env.example` khi triển khai cấu hình.
- Raw có thông tin khách hàng: hạn chế quyền và không commit/export công khai.
- Gold serving mặc định bỏ email, tên và birth date; chỉ giữ thuộc tính cần thiết cùng định danh phân tích.
- LLM nhận mô tả schema/metric và SQL examples đã duyệt, không tự động nhận raw rows hoặc PII.
- Executor phân tích toàn bộ AST bằng dialect DuckDB; allowlist relation, column và function; chỉ một query được phép.
- Read-only connection đi cùng sandbox filesystem/network, chặn external access/extension loading và giới hạn thời gian, bộ nhớ, số dòng.
- Không coi SQLGlot, prompt hoặc read-only là ranh giới bảo mật duy nhất.
- Log prompt/SQL cần chính sách loại thông tin nhạy cảm; model Gemini cụ thể được cấu hình và xác nhận availability/pricing ở thời điểm tích hợp.

## Ngoài phạm vi MVP

Log-based CDC, hard-delete propagation, Kafka, Iceberg/Delta, cloud deployment, multi-user warehouse service, SCD2 lịch sử đầy đủ và mô hình churn được huấn luyện. Không tuyên bố exactly-once; mục tiêu là kết quả nghiệp vụ idempotent khi batch được xử lý lại.

## Tham chiếu

- [Dataset schema](https://dataset.xomdata.com/datasets/schema/e_commerce)
- [dlt filesystem](https://dlthub.com/docs/dlt-ecosystem/destinations/filesystem)
- [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency)
- [DuckDB security](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview)
- [Airflow Docker Compose](https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html)
- [Airflow best practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)
