# Runtime data local

Thư mục này giữ đầu vào và runtime artifacts local. Đã có 4 CSV ở `bootstrap/`; chưa có artifacts do pipeline sinh ra.

- `bootstrap/`: snapshot đầu vào được lấy hợp lệ; có thể chứa PII, không commit.
- `warehouse/`: file DuckDB build và metadata local; một writer tại một thời điểm.
- `serving/`: releases Gold bất biến, release metadata và pointer active.

Raw archive chính nằm trong MinIO, theo layout trong [data flow](../docs/data-flow.md). Compose volumes cho Postgres/MinIO/Dagster sẽ được cấu hình ở chặng implementation, không mặc định trỏ vào những thư mục này.

`.gitignore` loại payload runtime; chỉ README và `.gitkeep` được giữ. Dữ liệu giả lập dùng cho tests nằm ở `tests/fixtures/`, không sao chép dữ liệu khách hàng thật vào đó.

Theo [ingestion plan](../docs/ingestion-plan.md), CSV gốc sẽ mount read-only vào runtime để bootstrap Postgres; dlt đọc từ Postgres và commit raw Parquet lên MinIO. `.dockerignore` cũng loại `data/` khỏi build context.
