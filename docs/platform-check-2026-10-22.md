# Kiểm tra Docker và shared platform · 2026-10-22

> **Audit lịch sử, không phải kiến trúc hiện hành.** Từ 2026-10-23 chọn CSV → PostgreSQL source → DuckDB → dbt-duckdb → marts; không dùng MinIO. Đánh giá MinIO dưới đây thuộc thiết kế trước; xem [architecture hiện hành](architecture.md). Không có audit live mới trong lần cập nhật kiến trúc.

> Snapshot lúc 11:19 UTC+7 trước khi BrewLite được quản lý tài nguyên. Cấu hình hiện tại đã đăng ký BrewLite 512 MiB và chuyển dashboard LaplapTech sang bật khi cần; xem D:/Dev/Project/laplaptech_pipeline/docs/validation/brewlite_resource_2026-10-22.json và policy vận hành trước khi triển khai e-commerce.

## Nguồn quy ước đã đọc

- [AGENTS của platform](D:/Dev/Project/airflow-platform/AGENTS.md)
- [Runbook onboarding/tài nguyên](D:/Dev/Project/laplaptech_pipeline/docs/guides/resources.md)
- [Registry vận hành](D:/Dev/Project/airflow-platform/resources.json)
- `compose.yaml`, `compose.laplaptech.yaml`, `budget_docker.py`, `platform_resource_policy.py` và script audit ở platform local.

Đây là cấu hình local đang vận hành; không mặc định bản template GitHub luôn khớp với máy này.

## Kết quả live

Audit lúc **2026-10-22 11:19:21 UTC+7** bằng script có sẵn `check_resources.py`: **success**, không có errors cho các service/pool được quản lý.

| Thành phần | Kết quả |
| --- | --- |
| Docker Engine | 6 CPU; RAM Engine báo 7942 MiB |
| Airflow API / scheduler / DAG processor | Cả 3 healthy, không OOM, restart count 0 |
| Metadata PostgreSQL | Healthy; giữ riêng `airflow_meta` |
| Shared warehouse PostgreSQL | `warehouse-laplaptech`, healthy, limit 1024 MiB / 1,5 CPU |
| Dashboard LaplapTech | Healthy |
| Pool chung | `platform_memory`, 4 slots × 512 MiB |
| E-commerce registry | Chưa có project `ecom` |
| Database / roles e-commerce | Query chỉ đọc `ecom%` chưa thấy database hoặc role; chưa provision |
| Ngoài registry | Có `brewlite-db` đang chạy; Docker Memory/NanoCpus đều 0, nghĩa là chưa đặt trần tương ứng |

Báo cáo JSON local ở `data/local-checks/platform-resource-check-2026-10-22.json`, được ignore bởi quy tắc `data/`. Audit success **chỉ bao phủ các containers/pool trong policy**, không chứng minh mọi workload ngoài registry đã được tính ngân sách. Không dừng hoặc sửa `brewlite-db` trong lượt kiểm tra này.

## Ngân sách đã kiểm bằng validator thực tế

| Khoản | MiB |
| --- | ---: |
| Services thường trực đã đăng ký | 4608 |
| Task pool chung | 2048 |
| Headroom đã dành | 768 |
| VM overhead | 512 |
| Tổng host policy yêu cầu | **7936** |
| Trần WSL theo policy | **8192** |
| Phần chưa phân bổ | **256** |

Đây là phép tính theo **limits/ngân sách**, không phải số RAM thực đang rảnh. Không lấy headroom/swap làm phần mở rộng task một cách ngầm định. Docker Engine báo RAM khác trần WSL là hai số khác nhau; validator và audit có cách đối chiếu riêng.

Thử trên bản sao policy **trong bộ nhớ**, không sửa registry:

- Thêm tasks e-commerce dùng lại pool chung, chưa thêm service: validator pass; task cạnh tranh trong cùng 2048 MiB, không tạo thêm một pool 2048 MiB khác.
- Thêm MinIO thường trực giả định 512 MiB: yêu cầu **8448 > 8192 MiB**, validator từ chối.
- Thêm MinIO thường trực giả định 1024 MiB: yêu cầu **8960 > 8192 MiB**, validator từ chối.

Các mức MinIO trên là kịch bản kiểm budget, chưa phải RAM requirement đã đo của AIStor. Không ép limit xuống 256 MiB chỉ để làm phép tính pass. Muốn bật MinIO cần quyết định và đo lại tài nguyên; runtime/source smoke có thể chuẩn bị trước nhưng raw MinIO chưa được coi là sẵn sàng.

## Các thay đổi trong plan

1. Dùng chung Airflow **và PostgreSQL service**; không dựng thêm container `postgres-source` trên máy này.
2. Tạo database `ecom_source_dev` cùng owner/reader không superuser, độc lập database LaplapTech; không dùng `airflow_meta`.
3. Runtime join network `laplaptech-lab`, gọi `warehouse-laplaptech:5432`. MinIO khi được duyệt dùng service/alias riêng như `ecom-minio`.
4. Chuyển DAG mẫu sang `BudgetDockerOperator`, project/stage phải đăng ký trước khi DAG được mount/parse. Bỏ pool `ecom_writer` riêng.
5. Budget RAM/CPU lấy từ registry; single-writer dùng `max_active_runs=1`, `max_active_tasks=1` và file lock xuyên build/publish.
6. Persistent service mới phải được đăng ký và audit được. Nếu MinIO do shared platform quản lý, Compose service phải nằm trong project `airflow-platform` để khớp script audit hiện tại; JSON không tự tạo service.

Đã thêm [AGENTS.md của e-commerce](../AGENTS.md) để lần làm việc tiếp theo đọc đúng các quy ước này, đồng thời cập nhật [Docker plan](docker-plan.md) và các tài liệu liên quan.

Chưa tạo database/user, sửa `.env`/resource registry của platform, build image, deploy DAG, restart service hoặc bật MinIO trong lượt này.
