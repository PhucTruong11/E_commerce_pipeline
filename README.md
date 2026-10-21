# Xóm E-Com · Modern Data Pipeline

Pipeline ELT phục vụ phân tích doanh thu, lợi nhuận, chiết khấu và hành vi mua hàng từ dataset **Xóm E-Com**. Dự án ưu tiên chạy local, dữ liệu có thể truy vết và warehouse có thể dựng lại từ raw.

**Trạng thái: thiết kế và scaffold.** Repository hiện có tài liệu, sơ đồ SVG và khung thư mục; chưa có pipeline, dbt models, Docker Compose, dashboard hay CI chạy được. Các công cụ dưới đây là lựa chọn thiết kế, chưa phải tích hợp đã kiểm chứng.

## Data flow

![Luồng dữ liệu và điều phối Xóm E-Com](docs/diagrams/data-flow.svg)

**Stack dự kiến:** PostgreSQL · dlt · MinIO · DuckDB · dbt Core + dbt-duckdb · Apache Airflow · Streamlit · Gemini + SQLGlot.

- **PostgreSQL:** nguồn giao dịch giả lập từ snapshot dataset; bổ sung metadata để thử insert/update.
- **dlt → MinIO:** extract theo batch, lưu Parquet và manifest bất biến để audit/replay.
- **DuckDB + dbt:** Bronze giữ trạng thái đã đối soát; Silver chuẩn hóa; Gold phục vụ phân tích.
- **Airflow:** DAG mỏng điều phối ingestion và build/publish; code nghiệp vụ nằm ngoài DAG. dbt CLI trước, Cosmos là tùy chọn sau khi kiểm tra tương thích.
- **Streamlit / Text-to-SQL:** đọc bản serving đã publish; Gemini là phần mở rộng sau MVP.

## Dataset và giới hạn

Nguồn: [Xóm E-Com dataset](https://dataset.xomdata.com/datasets/schema/e_commerce). Schema công bố 4 bảng:

| Bảng | Vai trò | Khóa ứng viên cần profiling |
| --- | --- | --- |
| `ecom_sales` | Dòng bán hàng; có sales, discount, profit | `row_id` |
| `customer` | Thuộc tính khách hàng | `customer_id` |
| `product` | Danh mục sản phẩm | `product_code` |
| `region` | Địa lý và thị trường | `region_code` |

Không mặc định nguồn có PK/FK được enforce, `updated_at`, payments, returns hay web events. Postgres local là **bản mô phỏng**, không phải hệ quản trị được xác nhận của nguồn Xóm Data. Không sử dụng các insight Mr. Fuzzy, paid search hoặc funnel của dataset khác làm kết luận cho dự án này.

## Mục tiêu MVP

1. Nạp snapshot của 4 bảng, xác nhận grain và định nghĩa metric.
2. Mô phỏng thay đổi dữ liệu; nạp incremental cho sales, snapshot đầy đủ cho dimensions.
3. Lưu raw bất biến; retry và replay không nhân đôi kết quả nghiệp vụ.
4. Xây facts/dimensions và marts để trả lời [15 câu hỏi nghiệp vụ](docs/context.md).
5. Chỉ publish Gold sau khi vượt qua quality gate.
6. Dựng lại warehouse khi Postgres tắt, chỉ sử dụng raw và metadata đã lưu.

MVP dùng **batch incremental**, chưa triển khai log-based CDC. Full rebuild dbt là lựa chọn ban đầu; chỉ thêm incremental models khi có cơ chế xử lý đúng các khóa bị ảnh hưởng bởi update.

## Data modeling

![Grain và phụ thuộc giữa các model](docs/diagrams/model-flow.svg)

Quy ước: **Raw** là archive batch ở MinIO; **Bronze** là bảng nguồn trong DuckDB; **Silver** gồm `stg_*` và `int_*`; **Gold** gồm `dim_*`, `fct_*`, `mart_*`. Medallion diễn tả trách nhiệm xử lý, không yêu cầu mỗi lớp phải là một bản sao vật lý.

## Bắt đầu từ đâu?

Hiện tại chưa có lệnh `make up` hoặc `docker compose up` cho dự án. Trình tự triển khai nằm trong [roadmap](docs/roadmap.md).

Ngày 2026-10-21 đã có đủ 4 CSV local trong `data/bootstrap/`, tổng 100.889 dòng. Kiểm tra ban đầu xác nhận headers/số cột và các khóa ứng viên không rỗng/trùng; chưa phải kiểm định đầy đủ chất lượng hay metric. Bước kế tiếp là **CSV → bootstrap Postgres → dlt → raw MinIO**, theo [ingestion plan](docs/ingestion-plan.md). CSV gốc được ignore khỏi Git và Docker build context; runtime sẽ mount read-only khi triển khai.

Hai chế độ triển khai được thiết kế dùng chung code pipeline:

| Chế độ | Cách dùng dự kiến |
| --- | --- |
| **Airflow có sẵn** | Mount/copy DAG vào DAG folder; cài project runtime trên worker bằng custom image; cấu hình network, storage và Connections. Không dựng lại Airflow đang dùng. |
| **Standalone Docker Compose** | Người clone repo build image và khởi tạo cả Airflow, metadata DB, Postgres source, MinIO và dashboard trong stack riêng. |

Chỉ copy `.py` DAG là đủ **khi** môi trường Airflow đã có code, dependencies, credentials, kết nối và storage cần thiết. File DuckDB không phải một database server/container riêng. Xem [Airflow & Docker](docs/airflow-docker.md) để biết contract tích hợp và kế hoạch đóng gói.

| Tài liệu | Nội dung |
| --- | --- |
| [Architecture](docs/architecture.md) | Ranh giới thành phần, lựa chọn stack, giới hạn MVP |
| [Airflow & Docker](docs/airflow-docker.md) | Tận dụng Airflow hiện có và đóng gói standalone để chia sẻ repo |
| [Ingestion plan](docs/ingestion-plan.md) | Inventory 4 CSV, các bước bootstrap/ingest/raw và kiểm tra trước GitHub |
| [Data flow](docs/data-flow.md) | Batch contract, watermark, retry, replay và publish |
| [Data modeling](docs/data-modeling.md) | Grain, join, metric và quality tests |
| [Business context](docs/context.md) | 15 câu hỏi, model dự kiến, giả định cần xác nhận |
| [Project structure](docs/project-structure.md) | Cây thư mục thực tế và trách nhiệm từng phần |
| [Roadmap](docs/roadmap.md) | Các chặng triển khai và điều kiện hoàn thành |
| [Operations](docs/operations.md) | Runbook dự kiến, failure modes và phục hồi |

## Nguyên tắc triển khai

- Không ghi đè raw batch đã commit; không đọc file bằng wildcard bỏ qua manifest.
- Không dedup theo `(order_id, product_code)` nếu chưa chứng minh đó là khóa dòng.
- Không coi `sales` là gross hoặc net khi chưa xác nhận business definition.
- Mọi lần chạy RFM có `as_of_date` cố định; không phụ thuộc ngày thực thi máy.
- Serving chỉ đọc release đã kiểm tra, độc lập với file DuckDB đang được build.
- Không commit credentials, dữ liệu khách hàng hay file database. Fixtures trong CI dùng dữ liệu giả lập.

## Tài liệu nguồn

- [Xóm E-Com schema và business context](https://dataset.xomdata.com/datasets/schema/e_commerce)
- [dlt SQL database incremental loading](https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/advanced)
- [dlt filesystem destination](https://dlthub.com/docs/dlt-ecosystem/destinations/filesystem)
- [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency)
- [DuckDB security](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview)
- [Airflow Docker Compose và custom images](https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html)

Phiên bản thư viện sẽ được ghim và kiểm tra tương thích trong chặng triển khai hạ tầng.
