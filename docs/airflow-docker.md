# Contract Airflow / Docker

> Plan tích hợp DAG, cập nhật 2026-10-24. Runtime và DB/users đã triển khai theo [Docker runbook](docker.md); DAG chưa deploy. [Docker runbook](docker.md) ghi rõ phần hiện có và công việc còn lại.

## Cách nối với platform hiện có

Airflow chỉ điều phối; loader và dbt nằm trong image **ecom-runtime** riêng. Không cài project dependencies vào Airflow và không dựng control plane khác.

DAG đề xuất **ecom_analytics_refresh**, schedule=None, catchup=False, max_active_runs=1, max_active_tasks=1. Một task **refresh** dùng BudgetDockerOperator chạy: extract consistent PostgreSQL snapshot → DuckDB candidate → dbt build → reconcile → publish Gold release. Bootstrap CSV là command riêng chạy trước, không reset nguồn mỗi refresh.

Một task giữ runtime file lock trên build volume suốt luồng; mọi writer thủ công dùng cùng lock. Đóng loader DuckDB connection trước dbt subprocess. PostgreSQL extraction dùng cùng read-only repeatable-read transaction cho 4 bảng; serving đọc Gold release riêng.

## Hợp đồng triển khai

- Đăng ký resource_project=ecom / resource_stage=refresh trong registry vận hành trước khi mount DAG.
- Pool và Docker limits do operator chung gán. Không truyền lại pool, pool_slots, mem_limit hoặc cpus.
- Network laplaptech-lab; PostgreSQL warehouse-laplaptech:5432, database ecom_source_dev.
- Mount input/config read-only; build/release/artifacts volumes riêng của project; không mount Docker socket vào runtime.
- Credentials và profile thật không vào Git, image, XCom hoặc command arguments.
- Timeout/retry có giới hạn; chỉ coi run thành công khi dbt và reconciliation đạt.
- Không đưa DataFrame, raw records hoặc PII vào XCom.
- DAG tĩnh không cần Cosmos hoặc dynamic task mapping trong MVP.

DAG concurrency không bảo vệ CLI chạy ngoài Airflow. CLI cũng không tự được pool quản lý tài nguyên: phải dùng operator đăng ký hoặc một exclusive window khi platform đã drain.

## Tích hợp sau luồng phân tích

Trước tiên loader và dbt phải được kiểm chứng trong runtime có ngân sách. Resource ecom/refresh đã đăng ký; sau khi CLI đạt mới mount DAG/config riêng và thử một DAG run. Mọi thay đổi hạ tầng dùng chung tuân thủ quy trình drain trong AGENTS/platform runbook.

Dữ liệu lịch sử không mới theo ngày hiện tại; theo dõi last successful run và kỳ dữ liệu riêng, không dùng MAX(order_date) cũ làm báo động ingestion trễ.

CDC connector là thành phần riêng ở chặng sau, không giả định task Airflow theo batch là daemon streaming. Xem [CDC plan](cdc-plan.md).
