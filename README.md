# Xóm E-Com · Analytics pipeline

Học **PostgreSQL, DuckDB, dbt, Docker và Airflow** qua phân tích sales, profit, discount và hành vi mua hàng từ bốn CSV Xóm E-Com.

**Loader đã hoàn thiện:** bootstrap CSV atomic/idempotent và extractor snapshot PostgreSQL → DuckDB Bronze. Image đã build, 10 kiểm tra fixture đạt; đã nạp và đối soát đủ 100.889 dòng từ CSV → PostgreSQL → DuckDB Bronze. Bootstrap chạy lại trả skipped. Chưa có business models, insight hoặc DAG. Bắt đầu tại [hướng dẫn Docker](docs/docker.md) và [plan thực hành hôm nay](docs/plans/2026-10-24-bootstrap-extract.md).

## Luồng dự án

![Data flow PostgreSQL → DuckDB → dbt](docs/diagrams/data-flow.svg)

**CSV bootstrap → PostgreSQL source → Python consistent snapshot → DuckDB Bronze → dbt Silver/Gold → SQL và báo cáo.** Phần analytics là ELT; bootstrap có validate/parse trước load. PostgreSQL-only cũng đáp ứng quy mô hiện tại; giữ thêm DuckDB để học tách nguồn/phân tích và embedded OLAP. Xem [lý do, trade-offs và data flow chi tiết](docs/architecture.md).

DuckDB đã chạy trong container runtime, file dữ liệu giữ trên volume riêng; không cần thêm DuckDB server. PostgreSQL là service dùng chung, mỗi project có database/user riêng. Không dùng file DuckDB hoặc `.venv` của TikTok/Shopee cho repo này.

## Dữ liệu và grain

Nguồn: [Xóm E-Com](https://dataset.xomdata.com/datasets/schema/e_commerce). Inventory baseline local:

| CSV | Dòng | Khóa ứng viên / grain |
| --- | ---: | --- |
| `customer.csv` | 17.415 | Một `customer_id` |
| `product.csv` | 28.356 | Một `product_code`; cần xác nhận product identity |
| `region.csv` | 3.828 | Một `region_code` |
| `ecom_sales.csv` | 51.290 | Một `row_id`, không phải một order |

Tổng **100.889 dòng, khoảng 8,76 MiB**. Đã kiểm headers/width/PK/types/date/precision/null và orphan keys. Có 2 dòng sales không khớp product và 2 dòng không khớp region; giữ lại và báo cáo. Order scope, currency và ý nghĩa sales/profit còn cần xác minh. Không dedup tùy ý theo `order_id + product_code` hoặc công bố insight khi chưa có kiểm chứng.

## Cấu trúc chính

```text
e_commerce/
├── compose.shared.yaml       # runtime reader/owner tạm thời
├── requirements.in          # dependencies trực tiếp
├── requirements.lock.txt    # bộ phiên bản đã ghim
├── config/                  # env/profile mẫu; không có password thật
├── infra/docker/            # Dockerfile runtime
├── ingestion/               # contracts, runtime guards, snapshot loader
├── scripts/                 # setup/provision/CLI và bootstrap COPY
├── dbt/
│   ├── models/bronze/       # source declarations, Python nạp dữ liệu
│   ├── models/silver/       # staging và joins/intermediate
│   ├── models/gold/         # facts/dimensions/analytics marts
│   ├── analyses/            # SQL Q01–Q15; dbt build không tự chạy analyses
│   ├── macros/, tests/, seeds/reference/
├── orchestration/dags/      # DAG chưa triển khai
├── data/bootstrap/          # CSV local, không commit/bake vào image
├── analysis/reports/        # báo cáo đã rà PII, chưa có insight
├── tests/integration/       # rollback/retry/snapshot trên fixture Docker
└── docs/                    # kiến trúc, runbook, modeling và plan
```

`.env`, `.local/`, input CSV, `.duckdb`, artifacts/logs và dumps không commit. Docker dùng `ecom-dev-build`, `ecom-dev-releases`, `ecom-dev-artifacts`; các volume không nằm trong source. Config local nằm trong `.local/secrets/`; runtime không dùng credential admin LapLapTech. Có bản DuckDB private cho DataGrip trong `.local/datagrip/`; xem [hướng dẫn mở file](docs/docker.md#mở-duckdb-bằng-datagrip).

## Nên đọc gì?

| Muốn làm gì? | Tài liệu |
| --- | --- |
| Build/check môi trường, dbt debug, đăng nhập PG | [Docker runbook](docs/docker.md) |
| Bootstrap 4 CSV, extract Bronze và hiểu code loader | [Plan thực hành](docs/plans/2026-10-24-bootstrap-extract.md) |
| Hiểu Docker/DuckDB, ETL/ELT, source/warehouse và recovery | [Architecture + data flow](docs/architecture.md) |
| Xác định grain, metrics, models và tests | [Data modeling](docs/data-modeling.md) |
| Chọn câu hỏi và cách viết insight | [15 câu hỏi kinh doanh](docs/context.md) |
| Theo dõi thứ tự làm và checkpoint | [Roadmap](docs/roadmap.md) |
| Tích hợp Airflow sau khi CLI ổn | [Airflow contract](docs/airflow-docker.md) |
| Mở rộng OLTP/CDC sau snapshot | [CDC plan](docs/cdc-plan.md) |

Ưu tiên `fct_order_lines`, `fct_orders` và monthly/product/RFM marts; trả lời câu hỏi bằng SQL rồi viết 3–5 phát hiện có bằng chứng. Dashboard và basket làm sau khi metric/product identity đủ rõ. Không đặt lịch hai lần/ngày chỉ để chạy lại CSV tĩnh.

Máy maintainer dùng shared platform theo [AGENTS.md](AGENTS.md), database `ecom_source_dev`, roles `ecom_owner`/`ecom_reader`, resource `ecom/refresh`. Người clone phải cấu hình platform/credentials riêng; Compose standalone và quickstart end-to-end chưa triển khai. Không thêm MinIO, Kafka, Cosmos hoặc chatbot vào MVP hiện tại.
