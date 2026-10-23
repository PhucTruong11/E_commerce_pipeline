# Ingestion plan · CSV → PostgreSQL → DuckDB

> Snapshot trước, OLTP/CDC sau. Các mẫu dưới đây là thiết kế, chưa tạo loader mới hoặc cài dependencies.

## 1. Inventory

| CSV trong data/bootstrap | Dòng | Khóa ứng viên |
| --- | ---: | --- |
| customer.csv | 17.415 | customer_id |
| ecom_sales.csv | 51.290 | row_id |
| product.csv | 28.356 | product_code |
| region.csv | 3.828 | region_code |

Tổng 100.889 dòng, khoảng 8,76 MiB. Đã kiểm tra headers/width/khóa ứng viên; chưa hoàn tất type/FK/order/currency profiling. Không in customer records hoặc dedup product codes theo số SKU trong mô tả.

## 2. Bootstrap PostgreSQL một lần

File sẽ viết: **scripts/bootstrap/load_csv.py**; parser hiện có: **ingestion/sources/csv_contracts.py**; DDL dự kiến **infra/postgres/init/010_source_schema.sql**.

- Kiểm tra đủ 4 CSV, schema/types/keys/FK; hash đúng payload sẽ COPY.
- Guard database ecom_source_dev, user ecom_owner không superuser; chưa provision.
- DDL e_commerce gồm 4 bảng typed sau profiling; pipeline_meta ghi bootstrap_id/file hashes/counts.
- COPY qua psycopg, identifier allowlist; cả 4 bảng và inventory trong một transaction.
- Cùng bootstrap fingerprint thì skip, **không reset dữ liệu nguồn đã có OLTP changes**.
- CSV khác cần explicit new-baseline/reset workflow; không tự overwrite hoặc triển khai reset ở lượt này.

Hiện chỉ có parser csv_contracts.py; bootstrap 4 bảng và DDL nguồn sẽ viết mới. Mẫu bootstrap product/DDL cũ và dlt/MinIO đã đưa khỏi source trong lượt dọn scaffold. Các code blocks dưới đây vẫn là plan, không phải module đã triển khai.

## 3. Extract snapshot nhất quán

File dự kiến: **ingestion/loaders/postgres_to_duckdb.py**. Mẫu này minh họa đọc cả 4 bảng qua một snapshot. Caller phải mở connection PG autocommit=True, guard đúng ecom_source_dev/ecom_reader và giữ project file lock. write_batch là callback phải viết để nạp candidate DuckDB bằng parameterized inserts và DDL tường minh.

```python
from psycopg import sql
from ingestion.sources.csv_contracts import CONTRACTS

def extract_snapshot(pg_conn, write_batch):
    # Một transaction cho 4 bảng: không mở 4 connection độc lập.
    with pg_conn.transaction():
        pg_conn.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )
        for table, (_, headers) in CONTRACTS.items():
            statement = sql.SQL("SELECT {} FROM {}").format(
                sql.SQL(", ").join(sql.Identifier(c) for c in headers),
                sql.Identifier("e_commerce", table),
            )
            # Named cursor stream từ server, không fetchall toàn bảng.
            with pg_conn.cursor(name=f"extract_{table}") as cur:
                cur.execute(statement)
                while True:
                    rows = cur.fetchmany(1000)
                    if not rows:
                        break
                    write_batch(table, rows)
```

Callback ghi vào bronze của **candidate mới**, thêm extraction_id/source metadata và giữ Decimal/date theo contract, không stringify/float mất precision. Counts/totals trong transaction nguồn phải đối soát với candidate; snippet chưa bao gồm phần này. Lỗi bất kỳ bảng nào thì không activate candidate.

Source snapshot là initial/full extraction, không phải CDC. Snapshot identity sau khi nguồn thay đổi không được suy ra từ checksum CSV baseline.

## 4. Runtime, dbt và publish

File dự kiến: **scripts/run_pipeline.py**. Pseudocode, chưa có các helpers/CLI:

```python
def refresh(config):
    # Bootstrap là command riêng, không gọi lại để reset nguồn.
    validate_source_identity_and_paths(config)
    with project_file_lock(config):
        candidate = create_new_candidate(config)
        # Extract toàn bộ 4 nguồn bằng cùng snapshot PG.
        extract_and_load_bronze(config, candidate)
        reconcile_snapshot(config, candidate)
        close_loader_duckdb_connections(candidate)
        # dbt Core + dbt-duckdb trỏ đúng candidate, check=True.
        run_dbt_build(config, candidate)
        reconcile_facts(config, candidate)
        # Chỉ Gold, không copy nguyên file chứa Bronze/customer PII.
        release = export_gold_only(config, candidate)
        close_and_verify_read_only(release)
        switch_active_pointer_atomically(config, release)
```

File lock nằm trên volume build chia sẻ, giữ từ extract tới publish. Không giữ DuckDB writer connection của loader khi dbt subprocess ghi. Release có tên riêng bất biến; không overwrite file reader đang mở. Airflow concurrency không thay thế file lock cho CLI.

## 5. Acceptance trước insight

| Kịch bản | Điều kiện |
| --- | --- |
| Bootstrap lần đầu / retry | Đủ 4 bảng; không duplicate; retry không xóa OLTP changes |
| Input lỗi / thiếu bảng | Không commit source bootstrap dở |
| Source thay đổi giữa extract | 4 bảng phản ánh cùng PG snapshot |
| Extract/dbt/reconcile fail | Không đổi active Gold pointer |
| Hai writers | Lock ngăn ghi đè, có timeout |
| Retry full snapshot | Candidate mới; serving không append double count |
| Join/roll-up | Count/sales/profit khớp, orders đúng grain |
| Sai PG target / DuckDB path | Fail trước ghi |

Sau đó làm staging/facts và ba marts monthly/product/RFM. [CDC](cdc-plan.md) chỉ thêm sau khi đã có OLTP operations và snapshot pipeline ổn.

.gitignore/.dockerignore tiếp tục loại CSV, DuckDB, credentials, dbt profiles và artifacts. Không cần nới ignore; CI dùng synthetic fixtures.
