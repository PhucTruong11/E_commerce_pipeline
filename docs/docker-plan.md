# Docker plan: PostgreSQL source, DuckDB + dbt trong runtime

> Cập nhật lựa chọn PostgreSQL + DuckDB + dbt ngày 2026-10-23; không dùng MinIO. Hiện chỉ cập nhật plan/docs; chưa tạo role/database, sửa registry, build image, restart service hoặc chạy DAG.

## 1. Thành phần cần triển khai

| Thành phần | Trên máy này | Với người clone chưa có platform |
| --- | --- | --- |
| PostgreSQL | Service chung hiện có | Một service riêng trong Compose standalone |
| Runtime Python + dbt-duckdb | Image/container tạm thời ecom-runtime | Cùng image |
| Airflow | Platform hiện có | Không bắt buộc để chạy CLI |
| DuckDB | Embedded engine trong runtime; build/release volumes riêng | Cùng image và volumes riêng |
| MinIO | Không dùng | Không dùng |
| OLTP/CDC | Chặng sau; chưa deploy connector | Tùy chọn sau snapshot |
| Dashboard | Chưa triển khai | Thêm sau nếu cần |

Không cài Python packages trực tiếp trên host chỉ để chạy pipeline. Công cụ host tối thiểu cho người dùng là Docker; việc build image cần tải base image/packages.

## 2. Database và cấu hình riêng

Tên đề xuất, **chưa provision**:

| Mục | Giá trị |
| --- | --- |
| Database | ecom_source_dev |
| Owner/writer | ecom_owner, non-superuser |
| Reader | ecom_reader, non-superuser, SELECT 4 bảng nguồn |
| Schemas | PostgreSQL: e_commerce, pipeline_meta; DuckDB: bronze, staging, intermediate, marts |
| Container host/port | warehouse-laplaptech:5432 |
| Network | laplaptech-lab |
| Host endpoint | 127.0.0.1 và WAREHOUSE_HOST_PORT của platform |
| Resource project/stage | ecom / refresh |
| Runtime / DAG | ecom-runtime / ecom_analytics_refresh |

Tên nguồn ecom_source_dev thay đề xuất analytics một engine trước đó; không có thao tác rename/migrate trong lượt thiết kế này. Khi implementation, kiểm tra tồn tại/owner trước khi tạo; không ghi đè đối tượng đã có.

Dự kiến database CONNECTION LIMIT 8, writer 4, reader 2, dbt threads=1. Identity guard trước ghi phải xác nhận current_database/current_user, role không superuser và schema target. Không dùng admin LaplapTech hoặc database Airflow metadata. Reader là extractor nguồn, có quyền đọc dữ liệu cần ingestion; không dùng credential này cho BI.

Serving chỉ đọc file Gold-only đã publish, không mở file build/Bronze. Quyền truy cập file/volume tách khỏi PG extractor.

Config riêng dự kiến gồm PGHOST, PGPORT, PGDATABASE, PGUSER, password/secret file, INPUT_DIR, DBT_PROFILES_DIR, ARTIFACT_DIR, ANALYSIS_AS_OF_DATE. Guard PG target source và DuckDB candidate path riêng. dbt profile phải trỏ đúng candidate; không query nguồn PG qua dbt models.

## 3. Ngân sách đề xuất

Đã đọc registry vận hành 2026-10-23: chưa có project ecom; warehouse chung 1024 MiB, pool 4 slots × 512 MiB. Dashboard LaplapTech và BrewLite 512 MiB là optional services. Không kiểm chứng lại trạng thái container live trong lần sửa kiến trúc này.

JSON dưới đây là **đề xuất để review**, không phải thay đổi đã áp dụng:

```json
{
  "ecom": {
    "dbt_threads": 1,
    "services": {},
    "tasks": {
      "refresh": {"memory_mib": 1024, "cpus": 1}
    }
  }
}
```

refresh chiếm 2 slot trong pool hiện có; không tăng pool hoặc cộng thêm task pool mới. Không có service thường trực mới. Với một optional service 512 MiB chạy, phép tính policy là 4096 + 512 + 2048 task pool + 768 headroom + 512 overhead = 7936/8192 MiB. Hai optional services cùng chạy vượt ngân sách; cần audit trạng thái thực trước triển khai.

Đây là budget limits, không phải số RAM thực đang dùng. Extraction dùng tài nguyên PostgreSQL chung; DuckDB/dbt compute và spill thuộc runtime/volume. Bắt đầu dbt 1 thread; giới hạn DuckDB memory dưới container cap, dành phần cho Python/dbt và đo peak trước khi chốt. Runtime 1024 MiB là đề xuất chưa benchmark.

## 4. Các file sẽ viết

| File dự kiến | Vai trò |
| --- | --- |
| requirements.in + requirements.lock.txt | psycopg[binary], dbt-duckdb và bộ dependencies đã kiểm chứng |
| infra/docker/runtime.Dockerfile | Python runtime, copy source; không copy data/secrets |
| config/.env.example | Placeholder cấu hình riêng, không có mật khẩu thật |
| config/profiles.example.yml | dbt profile đọc env, target DuckDB candidate path |
| infra/postgres/init/010_source_schema.sql | Source/meta DDL cho cả 4 bảng, sẽ viết mới |
| scripts/run_pipeline.py | Guard, file lock, snapshot extract, dbt, reconciliation, publish |
| ingestion/loaders/postgres_to_duckdb.py | Đọc PG nhất quán và nạp Bronze vào candidate DuckDB |
| orchestration/dags/ecom_analytics.py | BudgetDockerOperator gọi runtime |
| compose.standalone.yaml | PostgreSQL + runtime cho người chưa có platform |

Đây là danh sách **chưa tạo**. Không có Dockerfile/Compose mới hoạt động trong repo lúc sửa plan. Dependency versions/base image sẽ ghim khi build được kiểm chứng, không đoán số phiên bản trong tài liệu.

## 5. Mẫu DAG dự kiến

File dự kiến: orchestration/dags/ecom_analytics.py. Skeleton minh họa chỉ phần hợp đồng operator; còn thiếu imports, DAG context, mounts, image đã build, command thực thi và config.

```python
# Không paste thành DAG chạy ngay: phải thêm context/config/mounts.
refresh = BudgetDockerOperator(
    task_id="refresh",
    resource_project="ecom",
    resource_stage="refresh",
    image="ecom-runtime:local-v1",
    command=["refresh"],
    network_mode="laplaptech-lab",
    docker_url="unix://var/run/docker.sock",
    api_version="auto",
    mount_tmp_dir=False,
    auto_remove="force",
    do_xcom_push=False,
    log_opts_max_size="10m",
    log_opts_max_file="3",
)
# Không thêm pool/pool_slots/mem_limit/cpus: policy cấp các giá trị đó.
```

Bootstrap CSV mount read-only vào runtime; build/release volumes riêng phải persistent và được share cùng path/lock giữa writers. Không tạo DuckDB server. Đường dẫn nguồn trên Docker daemon phải được kiểm chứng từ Windows/WSL. Config/secret mount riêng; artifacts writable riêng. Không mount socket vào runtime, không dùng volume/config LaplapTech.

## 6. Thứ tự implementation và nghiệm thu

1. Hoàn thiện data contract và DDL/bootstrap/extract smoke trên fixtures.
2. Build runtime, kiểm tra target/role/network/input mounts, pin dependencies.
3. Trong window platform đã drain: cấp DB/users và đăng ký task nếu chưa có; bảo toàn policy và dữ liệu dự án khác.
4. Chạy loader/dbt checks qua registered operator hoặc CLI trong exclusive window phù hợp.
5. Tích hợp DAG sau khi command refresh chạy đúng; audit resources/import errors rồi mới unpause.
6. Thêm Compose standalone và quickstart cho người clone sau khi luồng chính ổn định.

Dù thứ tự phát triển bắt đầu từ code, mọi chạy thử thật vào PostgreSQL chung vẫn cần đúng identity/budget. CDC connector, replication role/slot và wal_level chưa được cấu hình. Connector thường trực phải budget riêng; xem [CDC plan](cdc-plan.md). Không tự deploy từ tài liệu này. [Quy ước](../AGENTS.md), [audit lịch sử](platform-check-2026-10-22.md), [onboarding platform](D:/Dev/Project/laplaptech_pipeline/docs/guides/resources.md).
