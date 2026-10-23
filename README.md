# Xóm E-Com · Analytics pipeline

Dự án học **PostgreSQL, DuckDB, dbt, Docker và Airflow** thông qua commercial analytics: doanh thu, lợi nhuận, discount và hành vi mua hàng từ 4 CSV Xóm E-Com.

**Trạng thái: initial scaffold (2026-10-23).** Đã có cây thư mục, tài liệu/sơ đồ, 4 CSV local và parser kiểm tra cấu trúc CSV. Chưa có bootstrap/extractor hoàn chỉnh, dbt models, Docker runtime hoặc DAG chạy được; chưa tính insight kinh doanh.

## Luồng đã chọn

![PostgreSQL nguồn tới DuckDB và insight](docs/diagrams/data-flow.svg)

**CSV → PostgreSQL nguồn → Python snapshot extraction → DuckDB Bronze → dbt Core + dbt-duckdb → Silver/Gold → SQL và insight.**

- Giữ nguyên CSV gốc trong `data/bootstrap/`, mount read-only; checksum nhận diện bộ đầu vào.
- Python dùng csv/psycopg để bootstrap PostgreSQL một lần và extract snapshot nhất quán sang DuckDB.
- PostgreSQL dùng chung chứa database nguồn riêng; DuckDB file riêng chứa Bronze, staging/intermediate và Gold marts.
- dbt Core + dbt-duckdb xử lý SQL, lineage, documentation và data tests trong DuckDB.
- Docker đóng gói runtime của dự án. Airflow hiện có gọi runtime sau khi luồng chạy độc lập đã ổn định.
- SQL analyses và báo cáo insight là đầu ra MVP. Dashboard thêm sau khi metric đã chốt.

**Giữ PostgreSQL + DuckDB + dbt** để học ranh giới nguồn và phân tích. Snapshot/insight trước, OLTP lab và CDC là chặng mở rộng. Chưa dùng MinIO/S3, dlt, Kafka, Cosmos hoặc Text-to-SQL. Xem [quyết định kiến trúc](docs/architecture.md).

## Dữ liệu và grain

Nguồn: [Xóm E-Com](https://dataset.xomdata.com/datasets/schema/e_commerce). Inventory local đã ghi nhận:

| CSV | Dòng dữ liệu | Khóa ứng viên | Grain cần giữ |
| --- | ---: | --- | --- |
| `ecom_sales.csv` | 51.290 | `row_id` | Một dòng bán hàng nguồn |
| `customer.csv` | 17.415 | `customer_id` | Một khách hàng nguồn |
| `product.csv` | 28.356 | `product_code` | Một mã sản phẩm nguồn |
| `region.csv` | 3.828 | `region_code` | Một mã địa lý nguồn |

Tổng **100.889 dòng, khoảng 8,76 MiB**. Kiểm tra trước đã xác nhận headers, độ rộng dòng và các khóa ứng viên không rỗng/trùng. Chưa xác nhận đầy đủ kiểu dữ liệu, FK, scope order ID hoặc ý nghĩa sales/profit. Không đồng nhất product code với SKU trước khi profiling.

## Ưu tiên insight

1. Chốt grain, ngày dữ liệu, đơn vị tiền tệ và định nghĩa metric.
2. Bootstrap đủ 4 bảng nguồn; extract cùng snapshot PG vào DuckDB Bronze; retry không nhân đôi.
3. Xây `fct_order_lines`, `fct_orders` và ba mart đầu tiên: monthly performance, product performance, customer RFM.
4. Trả lời [15 câu hỏi](docs/context.md) bằng SQL; basket làm sau khi xác nhận product identity và đủ đơn đa sản phẩm.
5. Viết 3–5 phát hiện có bằng chứng, tác động kinh doanh, đề xuất hành động và giới hạn diễn giải.
6. Đóng gói runtime, tích hợp DAG dùng chung; dashboard là bước sau.

Full snapshot và full rebuild là mặc định ban đầu. Không tạo lịch chạy hai lần/ngày cho dữ liệu không thay đổi; DAG trước mắt chạy thủ công khi input hoặc SQL thay đổi.

## Platform và Docker

Dùng chung Airflow/PostgreSQL theo [AGENTS.md](AGENTS.md). Database đề xuất mới là **`ecom_source_dev`**, writer/owner `ecom_owner`, extraction reader `ecom_reader`; các tên này **chưa được provision**. Không sử dụng Airflow metadata hoặc credentials của LaplapTech.

Không thêm PostgreSQL container trên máy hiện tại. DuckDB là embedded engine trong runtime tạm thời, không phải server riêng; mọi task phải đăng ký ngân sách và chạy qua `BudgetDockerOperator` / pool `platform_memory`. Extraction dùng tài nguyên PostgreSQL chung; dbt/DuckDB dùng RAM/CPU runtime và dung lượng spill volume, cần đo khi triển khai.

Người clone chưa có platform có thể dùng Compose gồm một PostgreSQL và runtime ở chặng packaging; Airflow là tùy chọn. **Hiện chưa có lệnh quickstart chạy được.**

## Tài liệu

Buổi thực hành tiếp theo: [Plan ngày 01 · kiến thức, cách làm và code mẫu](docs/plans/2026-10-23-day-01.md).

| Tài liệu | Nội dung |
| --- | --- |
| [Architecture](docs/architecture.md) | Phân vai PostgreSQL nguồn, DuckDB analytics và dbt |
| [Data flow](docs/data-flow.md) | Snapshot, transaction, retry và build |
| [Ingestion plan](docs/ingestion-plan.md) | Inventory, file cần viết, ví dụ có chú thích |
| [Data modeling](docs/data-modeling.md) | Grain, metrics và quality gates |
| [Business context](docs/context.md) | 15 câu hỏi và đầu ra phân tích |
| [Roadmap](docs/roadmap.md) | Thứ tự làm và điều kiện hoàn thành |
| [Docker plan](docs/docker-plan.md) | Runtime, cấu hình và ngân sách dùng chung |
| [Airflow integration](docs/airflow-docker.md) | Contract DAG/operator |
| [Project structure](docs/project-structure.md) | Source hiện có và file dự kiến |
| [Commercial analysis](analysis/README.md) | Quy ước SQL và báo cáo insight |
| [Operations](docs/operations.md) | Retry, restore và giới hạn phục vụ |
| [OLTP và CDC](docs/cdc-plan.md) | Chặng mở rộng, WAL/checkpoint/delete và resource gates |

Không commit CSV khách hàng, credentials, database dump hoặc artifacts chứa PII. Các mẫu dlt/MinIO/Parquet và scaffold không dùng đã được đưa khỏi cây source vào vùng khôi phục local được ignore. Tài liệu hiện hành phản ánh kiến trúc đang chọn.

Kỹ thuật tham khảo: [Psycopg COPY](https://www.psycopg.org/psycopg3/docs/basic/copy.html), [dbt-duckdb](https://github.com/duckdb/dbt-duckdb), [dbt data tests](https://docs.getdbt.com/docs/build/data-tests).
