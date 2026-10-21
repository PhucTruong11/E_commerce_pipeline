# Airflow có sẵn và đóng gói Docker

> Quyết định thiết kế: dùng Apache Airflow thay Dagster. Tài liệu mô tả cách sẽ triển khai; chưa có DAG, Dockerfile hay Compose chạy được. Chưa xác nhận phiên bản/executor của Airflow trên máy.

## 1. Hai chế độ, một codebase

| | Tích hợp Airflow hiện có | Standalone cho người clone repo |
| --- | --- | --- |
| Airflow | Tái sử dụng scheduler/UI/metadata DB hiện có | Repo khởi tạo stack Airflow riêng |
| DAG | Mount `orchestration/dags/` vào DAG folder phù hợp | Bake/mount cùng DAG vào custom image |
| Runtime | Cài project package, dlt, dbt-duckdb và providers trên worker cần thiết | Build dependencies cố định trong image |
| Nguồn và lake | Dùng endpoints đã cấu hình; có thể dựng Postgres source + MinIO của repo | Compose cung cấp source DB + MinIO và init services |
| DuckDB | Worker được bố trí storage tương thích; single writer | Volume single-host chia sẻ giữa build và serving theo quyền phù hợp |
| Credentials | Airflow Connections/secrets và env runtime | `.env` local/secret files; chỉ commit example |
| Kiểm chứng | DAG import + chạy smoke test trên Airflow thực tế | Smoke test từ checkout mới và trạng thái volume trống |

Không có yêu cầu dựng một Airflow mới trên máy đang có Airflow. Tuy nhiên **copy DAG không đồng nghĩa mang theo môi trường chạy**. Code và dependencies phải có ở worker thực thi; dependencies parse-time phải có ở DAG processor/scheduler tương ứng. Đường dẫn trên Windows host không tự tồn tại bên trong Linux container.

## 2. Cách thực thi chọn cho MVP

Custom image kế thừa đúng Airflow version đã kiểm tra, chứa project runtime và một venv riêng cho dbt. DAG dùng operators tiêu chuẩn để gọi runtime/CLI. Không cài dependencies mỗi lần task chạy và không truy vấn nguồn ở DAG parse time.

```text
ecom_batch DAG (planned)
  extract_to_raw
      ↓
  validate_and_commit_raw
      ↓
  build_and_publish  [writer pool: 1 slot + runtime file lock]
      ├─ load Bronze + ledger
      ├─ dbt build: Silver → Gold + tests
      ├─ reconciliation / quality gate
      └─ publish immutable serving release
```

Writer lock giữ từ lúc load Bronze tới khi publish hoàn tất. Các bước bên trong `build_and_publish` là code/CLI trong cùng task, chưa phải các Airflow tasks độc lập. Retry task vẫn idempotent nhờ ledger và cùng manifest set. Tách chúng thành nhiều task sau này đòi hỏi run isolation hoặc lease bao phủ cả vòng build.

Giữa tasks chỉ truyền batch ID/manifest URI qua XCom; Parquet ở MinIO, dữ liệu lớn không đi qua metadata DB. Cấu hình dự kiến: `max_active_runs=1`, `catchup=False` cho demo, retry/timeouts có giới hạn, không mở schedule trước bootstrap. Backfill/replay có target và checkpoint riêng.

Cosmos là mở rộng khi cần biểu diễn dbt models thành Airflow tasks. Không bắt buộc để gọi `dbt build`; khi thêm phải kiểm tra version, imports, execution mode và concurrency của DuckDB. MVP không cần DockerOperator hoặc Docker-in-Docker: task chạy ngay trong Airflow runtime container.

## 3. Contract tích hợp Airflow đang dùng

Trước khi deploy DAG, xác nhận:

1. Airflow 2.x/3.x, Python version, executor và phiên bản providers để chọn đúng imports/API và constraints.
2. DAG folder thực tế và cách phân phối code tới scheduler/DAG processor/workers.
3. Custom image hoặc cách cài runtime vào đúng worker; không chỉ cài trên máy host.
4. Shared Docker network, service DNS và endpoints; `localhost` trong container trỏ tới chính container đó.
5. Volume build/release/state, đường dẫn trong container, quyền UID/GID và semantics file lock.
6. Airflow Connections cho source/MinIO, secrets runtime, writer pool một slot và queue/routing nếu cần.

Nếu stack hiện tại dùng Celery/Kubernetes, không giả định hai tasks có cùng local filesystem. MVP DuckDB nên chạy build trên một worker chuyên dụng có storage single-host; dữ liệu giữa extract/build trao đổi bằng manifest trên MinIO. Dashboard cần đọc được release storage đã publish. Nếu không bố trí được contract này, cần đổi thiết kế serving/storage trước khi chạy.

Không tự nâng cấp Airflow hoặc chạy metadata migrations vào stack hiện có. Profile/Compose standalone không được dùng để reset volumes của môi trường hiện có.

## 4. Đóng gói standalone để chia sẻ

Đóng gói là tập **images + Compose + config + bootstrap**, không phải gộp tất cả dịch vụ vào một container.

Các thành phần dự kiến:

- Airflow services theo phiên bản đã ghim; LocalExecutor single-host cho demo.
- Airflow metadata Postgres riêng, tách khỏi `postgres-source`.
- Postgres source simulator, MinIO và init job tạo bucket.
- Init job cho Airflow metadata/user/pool theo API của phiên bản đã chọn.
- Custom Airflow/runtime image có project code và dbt venv.
- Dashboard image đọc Gold releases; AI là profile tùy chọn để demo cơ bản không cần Gemini API key.
- Persistent volumes cho source, lake, Airflow metadata/logs, dlt state và build/releases.

`compose.yaml` sẽ là stack standalone. `compose.services.yaml` dự kiến chỉ dựng source/MinIO cho chế độ tích hợp; không chứa Airflow thứ hai. Tên service/network/port sẽ được cấu hình để tránh xung đột với môi trường đang chạy.

**Trải nghiệm đích sau implementation** — các lệnh dưới đây chưa dùng được trong scaffold hiện tại:

```bash
cp .env.example .env
# Điền cấu hình demo hoặc nguồn thật theo README.
docker compose up --build -d
# Init/health checks hoàn tất; trigger DAG theo hướng dẫn sẽ bổ sung.
```

Windows PowerShell sẽ có hướng dẫn `Copy-Item .env.example .env`. Không bắt người dùng Windows cài Make để chạy demo. Health checks/init dependencies phải bảo đảm services sẵn sàng, nhưng không thay thế retry trong pipeline.

Mục tiêu có **demo fixtures giả lập** đủ các tình huống insert/update và các quan hệ bảng để chạy mà không cần tài khoản Xóm Data. Fixtures không dùng để công bố insight của dataset thật. Chế độ dữ liệu thật yêu cầu snapshot hoặc credentials hợp lệ; Docker không tự cung cấp quyền truy cập nguồn hay dữ liệu được phép phân phối.

Compose dùng cho local learning/demo; không tuyên bố đây là bản production hardened. Phiên bản base images và dependency lock được kiểm tra cùng nhau; không dùng tag `latest` cho release chia sẻ.

## 5. Điều kiện bàn giao gói Docker

- Checkout mới → build/init thành công theo đúng hướng dẫn, không phụ thuộc absolute host paths của tác giả.
- DAG không import error; runtime tìm thấy dbt executable, code và profile.
- Một lần chạy tạo raw, Gold và release; dashboard chỉ thấy release hợp lệ.
- Restart containers vẫn giữ dữ liệu/state; chạy lại không nhân bản metric.
- Hai run/backfill không ghi đồng thời hoặc publish kết quả bị trộn.
- Reset standalone không chạm stack Airflow hiện có.
- Có `.dockerignore`, không bake `.env`, raw PII, Docker socket hoặc credentials vào image.

Hiện chỉ cam kết thiết kế hai chế độ. Chưa chạy Docker smoke test và chưa kiểm chứng việc tích hợp Airflow trên máy.

## Tham chiếu

- [Airflow Docker Compose và custom images](https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html)
- [Airflow best practices: dependencies, task retries và XCom](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)
- [Airflow pools](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/pools.html)
- [Cosmos execution modes](https://astronomer.github.io/astronomer-cosmos/guides/run_dbt/execution-modes.html)
