# Cấu trúc repository

Đây là **cây thư mục đã tạo** cho giai đoạn tài liệu/scaffold. `.gitkeep` chỉ giữ thư mục trống trong Git. Chưa có source code, deployment configs hoặc lệnh chạy pipeline.

```text
e_commerce/
├── README.md
├── .gitignore
├── .dockerignore
├── docs/
│   ├── architecture.md
│   ├── airflow-docker.md
│   ├── ingestion-plan.md
│   ├── data-flow.md
│   ├── data-modeling.md
│   ├── context.md
│   ├── project-structure.md
│   ├── roadmap.md
│   ├── operations.md
│   └── diagrams/
│       ├── data-flow.svg
│       └── model-flow.svg
├── infra/
│   ├── postgres/init/.gitkeep
│   └── minio/.gitkeep
├── ingestion/
│   ├── sources/.gitkeep
│   ├── raw/.gitkeep
│   └── loaders/.gitkeep
├── orchestration/
│   ├── dags/.gitkeep
│   ├── task_groups/.gitkeep
│   └── resources/.gitkeep
├── warehouse/
│   ├── models/
│   │   ├── sources/.gitkeep
│   │   ├── staging/.gitkeep
│   │   ├── intermediate/.gitkeep
│   │   └── marts/
│   │       ├── core/.gitkeep
│   │       └── analytics/.gitkeep
│   ├── analyses/.gitkeep
│   ├── macros/.gitkeep
│   ├── seeds/
│   │   ├── .gitkeep
│   │   └── reference/.gitkeep
│   └── tests/.gitkeep
├── serving/
│   ├── dashboard/.gitkeep
│   └── text_to_sql/.gitkeep
├── scripts/
│   ├── bootstrap/.gitkeep
│   ├── simulate/.gitkeep
│   └── replay/.gitkeep
├── tests/
│   ├── unit/.gitkeep
│   ├── integration/.gitkeep
│   └── fixtures/
│       ├── .gitkeep
│       └── synthetic/.gitkeep
├── data/
│   ├── README.md
│   ├── bootstrap/.gitkeep
│   ├── warehouse/.gitkeep
│   └── serving/.gitkeep
└── .github/
    └── workflows/.gitkeep
```

## Ranh giới trách nhiệm

| Đường dẫn | Nội dung sẽ triển khai |
| --- | --- |
| `infra/` | Init SQL, bucket bootstrap; Compose đặt ở root khi có implementation |
| `ingestion/sources/` | dlt source và cấu hình bảng/cursor |
| `ingestion/raw/` | Manifest, checksum, commit protocol |
| `ingestion/loaders/` | Raw → Bronze, snapshot/upsert và batch ledger |
| `orchestration/dags/` | DAG mỏng của dự án, mount vào DAG folder của Airflow |
| `orchestration/task_groups/` | Task factories/groups khi cần tách, không chứa business logic |
| `orchestration/resources/` | Connection IDs, paths và runtime configuration helpers |
| `warehouse/models/sources/` | dbt source YAML cho Bronze |
| `warehouse/models/staging/` | Cast, naming và chuẩn hóa Silver |
| `warehouse/models/intermediate/` | Join, order roll-up, order history và pairs |
| `warehouse/models/marts/core/` | Dimensions và facts Gold |
| `warehouse/models/marts/analytics/` | RFM, product, monthly, discount và basket marts |
| `warehouse/analyses/` | SQL trả lời Q01–Q15 |
| `warehouse/tests/` | dbt singular data tests; generic tests nằm trong YAML/macro khi triển khai |
| `warehouse/seeds/reference/` | CSV reference nhỏ đã rà soát; ngoại lệ có chủ đích trong ignore rules |
| `serving/` | Dashboard, schema context và executor được giới hạn |
| `scripts/` | Bootstrap nguồn, simulator và replay entry points |
| `tests/` | Python tests, contract/integration tests và fixtures giả lập |
| `tests/fixtures/synthetic/` | Chỉ dữ liệu tự tạo; không lấy customer/source records đưa vào Git |
| `data/` | Artifacts runtime local; payload không được commit |
| `.github/workflows/` | CI trên fixtures; `.gitkeep` không phải workflow |

## Các file chỉ tạo khi có implementation

`pyproject.toml`, dependency lockfile, `.env.example`, `compose.yaml` (standalone), `compose.services.yaml` (source/MinIO/runtime cho Airflow có sẵn), Dockerfiles cho runtime/Airflow/dashboard, `Makefile`, `warehouse/dbt_project.yml`, `warehouse/profiles.example.yml`, Airflow DAG và GitHub Actions YAML. `.dockerignore` đã có để ngăn dữ liệu/secrets đi vào build context.

Không tạo các file cấu hình trống để gây hiểu nhầm rằng hệ thống đã chạy được. Khi thêm implementation, cập nhật cây thư mục và quickstart cùng lúc.

4 CSV local ở `data/bootstrap/` không hiển thị trong cây source được commit. Xem inventory và phạm vi kiểm tra trong [ingestion plan](ingestion-plan.md).
