# Cây thư mục initial scaffold

Mục tiêu: học tech và commercial analytics với **PostgreSQL nguồn → DuckDB → dbt → SQL/insight**. Cây bên dưới đã tạo; thư mục chưa có code được giữ bằng .gitkeep. Chỉ parser CSV hiện có code thực thi, chưa có pipeline hoặc môi trường cài mới.

```text
e_commerce/
├── README.md
├── AGENTS.md
├── .gitignore
├── .dockerignore
├── .github/workflows/              # CI sẽ thêm sau
├── config/
│   └── README.md                   # quy ước env/profile riêng
├── data/
│   ├── README.md
│   ├── bootstrap/                  # 4 CSV local, không commit
│   ├── warehouse/                  # build/candidate DuckDB local
│   └── serving/                    # Gold-only releases local
├── docs/
│   ├── architecture.md
│   ├── data-flow.md
│   ├── data-modeling.md
│   ├── context.md                  # 15 câu hỏi và metric contracts
│   ├── ingestion-plan.md
│   ├── docker-plan.md
│   ├── airflow-docker.md
│   ├── operations.md
│   ├── roadmap.md
│   ├── cdc-plan.md                 # mở rộng sau snapshot/insight
│   ├── project-structure.md
│   ├── plans/2026-10-23-day-01.md  # bài học, cách làm, mẫu và checkpoint
│   ├── platform-check-2026-10-22.md # audit lịch sử được giữ
│   └── diagrams/
│       ├── data-flow.svg
│       └── model-flow.svg
├── infra/
│   ├── README.md
│   ├── docker/                     # runtime Dockerfile sẽ viết
│   ├── airflow/                    # overlay/mount DAG vào platform
│   └── postgres/init/              # source DDL sẽ viết
├── ingestion/
│   ├── sources/
│   │   └── csv_contracts.py         # parser được giữ
│   └── loaders/                    # PG snapshot → DuckDB Bronze
├── scripts/
│   ├── bootstrap/                  # CSV → PostgreSQL
│   └── simulate/                   # OLTP lab ở chặng sau
├── orchestration/
│   ├── dags/                       # DAG BudgetDockerOperator
│   └── resources/                  # helpers cấu hình task
├── warehouse/                      # dbt project, chưa có models
│   ├── models/
│   │   ├── sources/                # Bronze source YAML
│   │   ├── staging/
│   │   ├── intermediate/
│   │   └── marts/
│   │       ├── core/               # dimensions, facts
│   │       └── analytics/          # monthly, product, RFM; basket sau
│   ├── analyses/                   # SQL Q01–Q15
│   ├── macros/
│   ├── seeds/reference/            # reference nhỏ đã rà soát
│   └── tests/                      # dbt data tests
├── analysis/
│   ├── README.md
│   └── reports/                    # báo cáo đã rà soát, không PII
├── serving/dashboard/              # tùy chọn sau insight
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/synthetic/         # chỉ dữ liệu tự tạo
```

.git và .local recovery được bỏ khỏi sơ đồ. data/local-checks giữ audit JSON local trước đây, được ignore. Không đụng dữ liệu hoặc hạ tầng của dự án khác.

## File sẽ viết khi implementation

| File dự kiến | Vai trò |
| --- | --- |
| scripts/bootstrap/load_csv.py | Bootstrap đủ 4 bảng trong transaction |
| ingestion/loaders/postgres_to_duckdb.py | Consistent extraction bằng source reader |
| scripts/run_pipeline.py | Guard, file lock, dbt, reconciliation và publish |
| infra/postgres/init/010_source_schema.sql | Source/meta DDL |
| warehouse/dbt_project.yml | Project dbt Core + dbt-duckdb |
| warehouse/models/sources/bronze.yml | 4 nguồn Bronze trong DuckDB |
| warehouse/models/staging/stg_*.sql | Typed views |
| warehouse/models/marts/core/fct_*.sql | Facts line/order đúng grain |
| warehouse/models/marts/analytics/mart_*.sql | Monthly/product/RFM |
| requirements.in + requirements.lock.txt | Dependencies ghim sau kiểm chứng |
| infra/docker/runtime.Dockerfile | Runtime riêng của project |
| config/.env.example + config/profiles.example.yml | Mẫu cấu hình không chứa secrets |
| orchestration/dags/ecom_analytics.py | DAG gọi registered operator |
| compose.standalone.yaml | PostgreSQL + runtime cho người clone |

Chưa tạo các file cấu hình/entrypoints rỗng có tên như đã chạy được. Không cài môi trường, build image, tạo DB/roles hoặc deploy DAG trong lượt scaffold này.

warehouse/analyses là SQL phục vụ Q01–Q15; dbt compile chúng nhưng dbt build không tự chạy analyses. analysis/reports giữ diễn giải kinh doanh, khác artifacts chứa dữ liệu local trong reports/ hoặc data/.

dbt schema mapping cần kiểm chứng khi implementation; custom schema mặc định có thể được ghép với target schema. DuckDB loader phải đóng connection trước khi dbt subprocess ghi candidate.

## Phần đã đưa khỏi source

dlt/MinIO, Parquet manifest/commit, bootstrap product/DDL cũ, Text-to-SQL, task_groups, replay scaffold, archive plan cũ và PNG render tạm đã chuyển vào .local recovery được Git/Docker ignore. Nội dung được giữ để khôi phục; không nằm trong source đang phát triển.

Audit lịch sử được giữ ở vị trí cũ; [kiến trúc](architecture.md) và [roadmap](roadmap.md) là plan hiện hành. [CDC](cdc-plan.md) là chặng học sau, chưa có connector.
