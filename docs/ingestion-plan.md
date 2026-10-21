# Plan: CSV bootstrap → ingestion → raw

> Lập ngày 2026-10-21. Đây là plan trước implementation; chưa có pipeline, image hoặc Compose chạy được. Đã kiểm tra file inventory, số dòng, độ rộng dòng và khóa ứng viên bằng CSV parser; chưa kiểm chứng đầy đủ kiểu dữ liệu, FK hay business semantics.

## 1. Dữ liệu local đã có

| File trong `data/bootstrap/` | Dòng dữ liệu | Cột | Khóa ứng viên | Rỗng / trùng khóa |
| --- | ---: | ---: | --- | --- |
| `customer.csv` | 17.415 | 11 | `customer_id` | 0 / 0 |
| `ecom_sales.csv` | 51.290 | 11 | `row_id` | 0 / 0 |
| `product.csv` | 28.356 | 4 | `product_code` | 0 / 0 |
| `region.csv` | 3.828 | 8 | `region_code` | 0 / 0 |

Tổng **100.889 dòng**, khoảng **8,76 MiB** theo kích thước file. CSV đọc được bằng `utf-8-sig`, dấu phân cách comma; không thấy dòng sai số cột trong lần kiểm tra. `utf-8-sig` xử lý được cả trường hợp có/không BOM, không khẳng định mọi file đều có BOM. Không in dữ liệu cá nhân vào báo cáo.

Quan trọng: `product_code` hiện unique trên 28.356 dòng. Không dedup xuống ~1.900 mã chỉ vì mô tả tham khảo nói có khoảng 1.900 SKUs. Cần kiểm tra quan hệ mã/tên sản phẩm để quyết định cách diễn giải SKU; chưa thay đổi mã nguồn hoặc gộp sản phẩm.

## 2. Phạm vi bước tiếp theo

```text
4 CSV local (read-only)
    → kiểm tra đầu vào + fingerprint
    → bootstrap PostgreSQL source giả lập
    → dlt SQL extraction (full snapshot)
    → MinIO raw Parquet + schema + manifest + _SUCCESS
```

Giữ kiến trúc Postgres → dlt → MinIO đã chốt. CSV là đầu vào bootstrap, chưa phải một nguồn CDC hoặc incremental thực tế. Bước này dừng ở raw: chưa load Bronze, viết dbt, dashboard hay tích hợp Gemini. Airflow được nối vào sau khi runtime/CLI chạy độc lập ổn định.

Không sửa hoặc overwrite CSV gốc. Có thể lưu checksum để nhận diện snapshot bootstrap; nếu sau này cần archive nguyên file CSV từng byte thì đặt vùng archive riêng và cập nhật contract, không ngầm coi Parquet là bản sao byte-for-byte.

## 3. Thứ tự triển khai và điều kiện hoàn thành

### A. Kiểm tra contract đầu vào

- Xác nhận đúng 4 tên file và headers; giữ một mapping/schema khai báo tường minh.
- Kiểm tra encoding, delimiter, null markers và format ngày; không để parser tự đổi customer/product codes thành số.
- Kiểm tra parse `quantity`, `sales`, `discount`, `profit`, `annual_income` và tọa độ; tiền dùng decimal với precision/scale xác nhận từ dữ liệu và nguồn.
- Kiểm tra FK từ sales tới customer/product/region; ghi số vi phạm, không log giá trị cá nhân.
- Kiểm tra scope order ID, header consistency, date range và mapping product code/name. Unique trên snapshot không tự chứng minh business identity lâu dài.
- Ghi checksum file, row count, schema version và các quyết định còn mở vào inventory. Nếu có lỗi, tạo báo cáo/quarantine local; không âm thầm bỏ dòng.

**Đạt khi:** contract parse và phương án xử lý lỗi được chốt; những kiểm tra đã chạy phân biệt rõ với giả định.

### B. Runtime Docker tối thiểu

- Thêm `pyproject.toml` + lockfile, Dockerfile runtime và `.env.example` không có credentials thật.
- Thêm `compose.services.yaml`: Postgres source, MinIO, bucket init và service runtime cho bootstrap/ingestion.
- Mount `data/bootstrap/` read-only vào runtime; đường dẫn trong container cấu hình được.
- Named volumes riêng cho Postgres, MinIO và state dlt; services dùng Docker DNS, không dùng `localhost` để gọi container khác.
- Health checks, init idempotent, log rotation; tránh trùng host port/network/volume với Airflow có sẵn.
- Secrets lấy từ env/secret files runtime. `.gitignore` và `.dockerignore` đã tạo ranh giới đầu tiên, chưa thay thế việc rà nội dung cấu hình.

**Đạt khi:** runtime nhìn thấy 4 CSV và kết nối Postgres/MinIO bằng CLI smoke check; restart giữ dữ liệu/state; không cần cài Python packages trực tiếp trên host.

### C. Bootstrap Postgres

- Tạo bảng theo schema đã xác nhận; load đủ 4 file trong transaction phù hợp.
- Ghi bootstrap snapshot ID từ checksum set và schema version; đối soát count và decimal/date round-trip.
- Chạy lại cùng snapshot không append duplicate. Input khác hoặc database đã có dữ liệu mô phỏng cần explicit mode; không tự truncate nguồn đang dùng.
- Metadata như `source_updated_at` / `source_version` là metadata giả lập, không có sẵn trong CSV nguồn. Chưa dùng `order_date` làm cursor thay đổi.
- Có account đọc riêng cho ingestion khi triển khai quyền.

**Đạt khi:** 4 bảng khớp count với CSV, keys không lỗi; bootstrap lần hai không nhân bản dữ liệu.

### D. dlt extraction và raw commit

- Dùng dlt SQL source extract full snapshot, ghi Parquet append theo batch. Chưa bật merge trên raw files.
- Raw layout thống nhất với [data flow](data-flow.md): bảng / extract date / batch ID.
- Mỗi batch có schema, checksum các file Parquet, row count và manifest; lưu source/bootstrap lineage và cấu hình cần để replay.
- Chỉ ghi `_SUCCESS` sau khi xác minh đủ payload và manifest; downstream không đọc batch dở dang.
- Retry cùng request/batch ID phải xác minh rồi skip/resume an toàn; không append vào batch đã committed.
- Run snapshot mới có thể tạo batch mới hợp lệ dù dữ liệu không đổi. Idempotence nghiệp vụ ở Bronze sẽ được bảo đảm bằng ledger/snapshot replace ở chặng sau, không tuyên bố raw không bao giờ có snapshot lặp.
- Nếu 4 bảng commit riêng, ghi một snapshot-set manifest liệt kê cả 4 table batches và chỉ đánh dấu set hoàn tất khi đủ; pipeline downstream nhận đúng set đã chốt.

**Đạt khi:** cả 4 bảng có raw committed, count khớp Postgres/CSV cho initial load, checksum đọc lại đúng; fail giữa upload không tạo batch/set hoàn tất giả.

### E. Tests cần có khi implementation tồn tại

Fixtures tự tạo, không cắt dòng từ customer.csv để đưa lên GitHub:

1. Headers thiếu/sai, malformed CSV hoặc parse sai tiền/ngày phải fail có thông tin rõ.
2. Duplicate/missing keys và orphan FK được phát hiện theo contract.
3. Decimal giữ đúng qua CSV → Postgres → Parquet; Unicode/codes không bị mất ký tự.
4. Bootstrap cùng input không tạo thêm dòng.
5. Retry batch đã commit không overwrite raw; corrupted checksum bị chặn.
6. Lỗi trước `_SUCCESS` hoặc trước snapshot-set commit không làm downstream nhận dữ liệu dở dang.

Chạy tests trong runtime và integration với Postgres/MinIO trước khi nối DAG. Chưa tạo tests giả cho code chưa có.

## 4. Sau khi initial snapshot đạt

Thêm simulator insert/update, cursor đáng tin, khoảng overlap và state recovery; sau đó Raw → Bronze → dbt và Airflow DAG mỏng. Nguồn CSV hiện tại chưa có `updated_at`, nên không gọi initial load này là CDC.

## 5. Chuẩn bị GitHub

- 4 CSV trong `data/bootstrap/` được ignore. Không dùng `git add -f` để đưa chúng lên repo.
- Commit code, docs, SVG, config templates và directory markers.
- CSV được phép commit chỉ ở `tests/fixtures/synthetic/` và `warehouse/seeds/reference/`; phải là dữ liệu giả lập/reference đã được rà soát, không chứa source/customer records.
- Config/manifest JSON không bị chặn hàng loạt; manifests runtime phải nằm trong `data/`, volume hoặc MinIO để không lẫn vào source.
- Lockfile dependencies cần commit khi được tạo; runtime state, DB files, secrets và logs không commit.
- Chưa thêm LICENSE mặc định: cần chọn license cho code và xác nhận điều kiện phân phối dataset riêng.
- Chưa init Git hoặc tạo remote. Ignore patterns được kiểm tra bằng Git trong một repo kiểm chứng tạm ngoài project.

Sau khi tự init, kiểm tra trước commit/push:

```powershell
git check-ignore -v data/bootstrap/customer.csv data/bootstrap/ecom_sales.csv data/bootstrap/product.csv data/bootstrap/region.csv
git status --short --ignored
git add --dry-run .
# Sau khi chọn và stage các file mong muốn:
git diff --cached --name-only
git diff --cached
```

`.gitignore` không gỡ file đã tracked và không phát hiện secrets nằm trong file được phép commit. Chưa có commit/index hiện tại, nên chưa có lịch sử cần gỡ dữ liệu.

Tham chiếu: [gitignore](https://git-scm.com/docs/gitignore), [git check-ignore](https://git-scm.com/docs/git-check-ignore).

## 6. Code mẫu để chuyển plan thành implementation

Các ví dụ dưới đây nằm **trong tài liệu**, chưa được tạo thành modules chạy thật. Python được viết theo Python 3.11+; dependencies dự kiến là `psycopg`, `dlt`, SQLAlchemy/Postgres driver, PyArrow và boto3. Chưa ghim versions hay cài chúng vào môi trường. Phải hoàn tất các phần còn thiếu và integration tests trước khi chạy pipeline.

| Ví dụ | File dự kiến khi implementation |
| --- | --- |
| Contract CSV + fingerprint | `ingestion/sources/csv_contracts.py` |
| DDL nguồn và bootstrap ledger | `infra/postgres/init/001_source_schema.sql` |
| Bootstrap một bảng | `scripts/bootstrap/load_csv.py` |
| Template biến môi trường | `.env.example` ở root repo |
| Postgres → dlt → MinIO | `ingestion/sources/postgres.py` |
| Parquet metadata + manifest | `ingestion/raw/manifest.py` |
| Commit marker và immutable metadata | `ingestion/raw/commit.py` |

**Cách đọc:** các đường dẫn dưới đây đều tính từ root repository. Đây là vị trí **dự kiến tạo file khi triển khai**, không phải các module đã tồn tại. Mỗi code block có chú thích tên file ngay đầu để có thể nhận diện khi copy riêng. Riêng JSON manifest là **output runtime trong MinIO**, không phải file cấu hình cần commit lên Git.

Luồng gọi dự kiến: CLI bootstrap gọi `csv_contracts.py` rồi `load_csv.py`; CLI ingestion gọi `postgres.py`, thu thập file từ dlt, dùng `manifest.py` để lấy metadata, rồi gọi `commit.py`. Airflow sau này gọi CLI/runtime này. Các hàm bên dưới chưa tự chạy chỉ bằng việc import module; entrypoint CLI và phần nối giữa chúng vẫn cần viết.

### 6.1. Kiểm tra CSV và fingerprint

**File dự kiến:** `ingestion/sources/csv_contracts.py` — contract dùng chung cho bootstrap và extraction.

**Đầu vào → đầu ra:** đường dẫn CSV + tên bảng → `(records, inventory)`. `records` là danh sách dictionary giữ giá trị dạng chuỗi; `inventory` chứa số dòng, checksum file và phiên bản contract. Hàm chỉ đọc file, không ghi database.

Ví dụ kiểm tra chính xác headers, số cột và khóa của cả 4 bảng. Snapshot hiện nhỏ nên ví dụ giữ records trong RAM; implementation có thể chuyển sang streaming/chunks. Checksum và records lấy từ **cùng một payload**, tránh hash một lần rồi đọc lại một phiên bản file khác.

```python
# File dự kiến: ingestion/sources/csv_contracts.py
# Vai trò: kiểm tra cấu trúc CSV và tạo fingerprint cho snapshot đầu vào.
import csv
import hashlib
import io
from pathlib import Path

# Mỗi entry: tên bảng -> (khóa ứng viên, danh sách cột THEO ĐÚNG THỨ TỰ).
# Dùng chung mapping này để parser và COPY không hiểu khác nhau về thứ tự cột.
CONTRACTS = {
    "customer": ("customer_id", [
        "customer_id", "first_name", "last_name", "birth_date",
        "marital_status", "gender", "email_address", "annual_income",
        "education_level", "occupation", "home_owner",
    ]),
    "ecom_sales": ("row_id", [
        "row_id", "order_id", "order_date", "customer_id", "segment",
        "region_code", "product_code", "quantity", "sales", "discount", "profit",
    ]),
    "product": ("product_code", [
        "product_code", "product", "category", "subcategory",
    ]),
    "region": ("region_code", [
        "region_code", "city", "state", "country", "country_latitude",
        "country_longitude", "region", "market",
    ]),
}


def read_checked_csv(path: Path, table: str):
    """Trả records và inventory; dừng bằng exception nếu cấu trúc/khóa sai.

    Chưa kiểm tra kiểu ngày, decimal, FK hoặc các quy tắc nghiệp vụ.
    Caller phải chọn table từ CONTRACTS; tên khác sẽ gây KeyError.
    """
    key, headers = CONTRACTS[table]
    # Đọc một lần: checksum và dữ liệu parse cùng xuất phát từ một bản bytes.
    # Mẫu giữ toàn bộ file/records trong RAM, phù hợp snapshot nhỏ hiện tại.
    payload = path.read_bytes()
    # utf-8-sig chấp nhận UTF-8 có hoặc không BOM.
    # csv.reader xử lý dấu phẩy/newline bên trong quoted field; không split(',').
    reader = csv.reader(
        io.StringIO(payload.decode("utf-8-sig"), newline=""),
        delimiter=",",
        strict=True,
    )
    # So cả tên và thứ tự cột; file rỗng cũng bị từ chối tại đây.
    if next(reader, None) != headers:
        raise ValueError(f"{table}: unexpected CSV headers")

    records, seen = [], set()  # seen chỉ tồn tại trong lần đọc file này.
    for record_number, values in enumerate(reader, start=2):
        if len(values) != len(headers):
            raise ValueError(f"{table}: invalid width at record {record_number}")
        row = dict(zip(headers, values))
        # Chỉ chuẩn hóa giá trị dùng để KIỂM TRA; row gốc không bị sửa.
        # Mã vẫn là chuỗi để giữ leading zero, ví dụ "00123".
        candidate = row[key].strip()
        if not candidate or candidate.casefold() == "null" or candidate in seen:
            # Không log nguyên row hoặc giá trị customer key.
            raise ValueError(f"{table}: invalid key at record {record_number}")
        seen.add(candidate)
        records.append(row)

    # SHA-256 nhận diện bytes của file, không phải checksum ngữ nghĩa của bảng:
    # đổi newline/thứ tự dòng có thể làm hash khác dù nội dung nghiệp vụ tương đương.
    return records, {
        "table": table,
        "row_count": len(records),
        "source_file_sha256": hashlib.sha256(payload).hexdigest(),
        "schema_version": "csv-v1",
    }
```

Hàm chỉ kiểm tra structural contract. Nó chưa parse ngày/decimal, kiểm tra FK hay biến chuỗi null thành SQL NULL. Whitespace dùng để kiểm tra khóa, không âm thầm sửa payload nguồn. Nếu phát hiện khóa có whitespace cần chốt policy trước bootstrap. Record number là số record CSV, không nhất thiết là physical line khi field có newline.

### 6.2. Bootstrap Postgres bằng transaction và COPY

**Hai file dự kiến:** `infra/postgres/init/001_source_schema.sql` tạo schema/bảng; `scripts/bootstrap/load_csv.py` chứa hàm nạp dữ liệu sau khi schema đã tồn tại.

**Đầu vào → đầu ra của Python:** `records, inventory` từ `read_checked_csv(..., "product")` → trạng thái `bootstrapped` hoặc `already_bootstrapped`. Side effect: ghi bảng product và ledger trong cùng transaction. Ví dụ chỉ triển khai một bảng để giải thích cơ chế.

Ví dụ cụ thể cho `product`, gồm schema text và ledger bootstrap. DDL này dự kiến chạy qua migration/init script bằng account bootstrap; ingestion dùng account read-only riêng.

```sql
-- File dự kiến: infra/postgres/init/001_source_schema.sql
-- Chạy bằng account bootstrap trước khi gọi hàm load trong Python.
-- e_commerce chứa dữ liệu nguồn; pipeline_meta chứa metadata do pipeline quản lý.
CREATE SCHEMA IF NOT EXISTS e_commerce;
CREATE SCHEMA IF NOT EXISTS pipeline_meta;

-- Dùng TEXT cho codes/nhãn sản phẩm; PRIMARY KEY chặn null và duplicate ở DB.
-- Đây chưa phải DDL cho đủ 4 bảng, cũng chưa khai báo quyền read-only.
CREATE TABLE IF NOT EXISTS e_commerce.product (
    product_code TEXT PRIMARY KEY,
    product TEXT,
    category TEXT,
    subcategory TEXT
);

-- Ledger ghi snapshot đã bootstrap thành công để tránh nạp lại CSV cùng bytes.
-- Khóa table_name nghĩa là mẫu này lưu một trạng thái bootstrap mỗi bảng,
-- không phải bảng lịch sử mọi lần chạy và không phải ledger raw ingestion.
CREATE TABLE IF NOT EXISTS pipeline_meta.bootstrap_snapshots (
    table_name TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    row_count BIGINT NOT NULL CHECK (row_count >= 0)
);
```

`BOOTSTRAP_PG_DSN` là URI libpq dạng `postgresql://...`, không dùng tiền tố SQLAlchemy `postgresql+psycopg://...` cho `psycopg.connect()`.

```python
# File dự kiến: scripts/bootstrap/load_csv.py
# Vai trò: load product đã validate vào nguồn Postgres giả lập.
import os
import psycopg

from ingestion.sources.csv_contracts import CONTRACTS


def bootstrap_product(records, inventory):
    """Nạp product một lần theo file fingerprint; trả trạng thái bootstrap.

    Yêu cầu: DDL đã chạy, records/inventory đến từ cùng lần validate CSV,
    BOOTSTRAP_PG_DSN đã được truyền vào environment của process.
    """
    # Kiểm tra nhầm bảng/số dòng; đây không thay thế kiểm tra toàn bộ schema.
    if inventory["table"] != "product" or inventory["row_count"] != len(records):
        raise ValueError("Unexpected product inventory")
    snapshot_id = inventory["source_file_sha256"]

    # Connection context commit khi thoát bình thường, rollback khi exception.
    # Không dùng autocommit: dữ liệu và ledger phải thành công/thất bại cùng nhau.
    with psycopg.connect(os.environ["BOOTSTRAP_PG_DSN"]) as conn:
        with conn.cursor() as cur:
            # Lock theo transaction; tự giải phóng khi commit/rollback.
            # 20261021 là ID lock quy ước của ví dụ, không phải snapshot ID.
            # Chỉ bảo vệ các writers cùng dùng protocol này, không chặn mọi SQL writer.
            cur.execute("SELECT pg_advisory_xact_lock(20261021)")
            cur.execute(
                "SELECT snapshot_id FROM pipeline_meta.bootstrap_snapshots "
                "WHERE table_name = %s",
                ("product",),
            )
            existing = cur.fetchone()  # Một tuple (snapshot_id,) hoặc None.
            if existing:
                if existing[0] == snapshot_id:
                    # Chỉ xác nhận đã nạp snapshot này trước đó.
                    # Không khẳng định dữ liệu hiện tại chưa bị simulator sửa.
                    return "already_bootstrapped"
                raise RuntimeError("Different snapshot: explicit reload mode required")

            # Có dữ liệu nhưng không có ledger: dừng để tránh trộn hai nguồn.
            cur.execute("SELECT EXISTS (SELECT 1 FROM e_commerce.product)")
            if cur.fetchone()[0]:
                raise RuntimeError("Refusing to overwrite existing source data")

            # COPY nhận Python values theo thứ tự cột, không nhận raw CSV bytes.
            # Psycopg xử lý escaping; không tự nối giá trị vào câu SQL.
            with cur.copy(
                "COPY e_commerce.product "
                "(product_code, product, category, subcategory) FROM STDIN"
            ) as copy:
                for row in records:
                    copy.write_row(tuple(row[c] for c in CONTRACTS["product"][1]))

            # Bảng đã được yêu cầu rỗng trước COPY nên count phải bằng toàn bộ input.
            cur.execute("SELECT COUNT(*) FROM e_commerce.product")
            if cur.fetchone()[0] != len(records):
                raise RuntimeError("Product row count mismatch")
            # Ghi ledger cuối transaction; lỗi INSERT cũng rollback dữ liệu vừa COPY.
            # %s + tuple là bind parameters của Psycopg, không phải f-string SQL.
            cur.execute(
                "INSERT INTO pipeline_meta.bootstrap_snapshots "
                "(table_name, snapshot_id, row_count) VALUES (%s, %s, %s)",
                ("product", snapshot_id, len(records)),
            )
    return "bootstrapped"
```

Ví dụ dùng `CONTRACTS` ở 6.1. `COPY.write_row()` sử dụng Python values, không thêm `FORMAT CSV` vào COPY này. Connection context commit khi thành công và rollback khi exception. Theo [Psycopg COPY](https://www.psycopg.org/psycopg3/docs/basic/copy.html).

Import `ingestion.sources.csv_contracts` giả định project package đã được cài trong runtime; chỉ copy một file Python riêng lẻ chưa đủ. Nếu mount SQL vào thư mục init của official Postgres image, init script chỉ chạy lúc khởi tạo data directory trống. Sửa file SQL sau đó không tự nâng cấp volume đang có; cần migration rõ ràng. `IF NOT EXISTS` cũng không xác nhận bảng đã có đúng schema mong muốn.

Nhánh `already_bootstrapped` chỉ ngăn nạp CSV lặp; chưa chứng minh current-state Postgres chưa bị simulator sửa. Không tự phục hồi nguồn từ CSV trong nhánh đó. Ledger mẫu dùng file checksum; implementation dùng snapshot-set fingerprint gồm cả 4 checksum và schema version. Để bootstrap 4 bảng nhất quán, refactor phần load từng bảng vào **cùng một connection/transaction**, load dimensions trước sales, rồi đối soát và commit một lần. DDL typed cho customer/region/sales, FK và policy null vẫn cần triển khai.

### 6.3. Extract full snapshot bằng dlt

**Hai file dự kiến:** `.env.example` mô tả cấu hình; `ingestion/sources/postgres.py` chứa hàm extraction. Người chạy tạo `.env` local từ template và Compose/CLI truyền biến vào process; `os.environ` không tự đọc file `.env`.

**Đầu vào → đầu ra:** batch UUID + ngày extract `YYYY-MM-DD` → `load_info` của dlt. Side effects: đọc Postgres, ghi Parquet vào MinIO và cập nhật dlt state trong volume. `load_info` chưa phải manifest đã được ứng dụng commit.

Ví dụ nhận batch ID và extract date từ caller để retry không tự đổi đường dẫn theo giờ máy. `RAW_BUCKET_URL` dự kiến dạng `s3://<bucket>/raw`; `dataset_name="e_commerce"` tạo lớp dataset bên dưới. Bucket phải được init trước.

```dotenv
# File dự kiến: .env.example (ở root repo; chỉ chứa placeholders).
# Tên biến và placeholders minh họa, không phải .env có thể chạy ngay.
# Account bootstrap được ghi schema/data; account reader chỉ đọc nguồn.
BOOTSTRAP_PG_DSN=postgresql://<bootstrap-user>:<password>@postgres-source:5432/ecom
SOURCE_DB_URL=postgresql+psycopg://<reader-user>:<password>@postgres-source:5432/ecom
RAW_BUCKET_URL=s3://<bucket>/raw
# State phải được mount vào persistent volume để giữ qua restart container.
DLT_PIPELINES_DIR=/app/state/dlt
# Namespace credentials dưới đây dành cho dlt filesystem destination.
# postgres-source và minio là Docker DNS names trên network dùng chung.
DESTINATION__FILESYSTEM__CREDENTIALS__ENDPOINT_URL=http://minio:9000
DESTINATION__FILESYSTEM__CREDENTIALS__AWS_ACCESS_KEY_ID=<access-key>
DESTINATION__FILESYSTEM__CREDENTIALS__AWS_SECRET_ACCESS_KEY=<secret-key>
DESTINATION__FILESYSTEM__CREDENTIALS__REGION_NAME=us-east-1
```

```python
# File dự kiến: ingestion/sources/postgres.py
# Vai trò: extract 4 bảng nguồn và để dlt ghi các payload Parquet lên MinIO.
import os
from datetime import date
from uuid import UUID

import dlt
from dlt.destinations import filesystem
from dlt.sources.sql_database import sql_database

from ingestion.sources.csv_contracts import CONTRACTS


def extract_snapshot(batch_id: str, extract_date: str):
    """Trả dlt load_info; chưa commit raw hoặc bảo đảm retry idempotent.

    Caller cấp ID/ngày ổn định, giữ lock state và kiểm tra marker trước khi gọi.
    """
    # Validate và chuẩn hóa trước khi đưa input vào object path.
    batch_id = str(UUID(batch_id))
    extract_date = date.fromisoformat(extract_date).isoformat()
    # SQLAlchemy URL dùng driver psycopg; chỉ đọc schema/bốn bảng đã khai báo.
    # PyArrow + reflection precision hỗ trợ chuyển kiểu; vẫn phải test round-trip
    # decimal/date thực tế, không coi lựa chọn backend là bằng chứng dữ liệu đúng.
    source = sql_database(
        credentials=os.environ["SOURCE_DB_URL"],
        schema="e_commerce",
        table_names=list(CONTRACTS),
        backend="pyarrow",
        reflection_level="full_with_precision",
    )
    # Prefix được chia theo table/date/batch; load_id/file_id do dlt cung cấp.
    # extract_date là ngày lấy dữ liệu, khác order_date của giao dịch.
    destination = filesystem(
        bucket_url=os.environ["RAW_BUCKET_URL"],
        layout=(
            "{table_name}/extract_date={extract_date}/batch_id={batch_id}/"
            "{load_id}.{file_id}.{ext}"
        ),
        extra_placeholders={"extract_date": extract_date, "batch_id": batch_id},
    )
    # Tên pipeline cố định + pipelines_dir bền vững định vị state của dlt.
    # Không cho nhiều process đồng thời thao tác cùng state directory.
    pipeline = dlt.pipeline(
        pipeline_name="ecom_snapshot",
        pipelines_dir=os.environ["DLT_PIPELINES_DIR"],
        dataset_name="e_commerce",
        destination=destination,
    )
    # append bảo toàn các file snapshot trước; KHÔNG merge theo business key.
    # Chạy lại không kiểm soát có thể tạo thêm files, dù batch_id không thay đổi.
    load_info = pipeline.run(
        source, write_disposition="append", loader_file_format="parquet"
    )
    # Chặn bước commit ứng dụng nếu dlt báo có job lỗi.
    # Thành công tại đây vẫn cần kiểm checksum/count/schema ở các bước sau.
    if load_info.has_failed_jobs:
        raise RuntimeError("dlt load has failed jobs; raw is not committed")
    return load_info
```

Ví dụ dùng `CONTRACTS` ở 6.1. Khi viết module thật phải import contract chung. Tham khảo [dlt SQL source](https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/usage) và [filesystem layout / MinIO credentials](https://dlthub.com/docs/dlt-ecosystem/destinations/filesystem).

Đoạn này **chỉ extract/load files**, chưa tạo application manifest hoặc `_SUCCESS`, chưa là CLI idempotent hoàn chỉnh. Caller cần lock pipeline state, chốt input batch, kiểm tra commit marker **trước khi gọi dlt**, và có resume protocol cho load dở dang. Không mặc định gọi lại `pipeline.run()` là không tạo file mới. Các bảng SQL có thể dùng các connection khác nhau: trong initial load phải dừng simulator/writes trong cả khoảng count → extract → đối soát; một batch ID không tự bảo đảm shared DB snapshot.

### 6.4. Metadata Parquet và manifest mẫu

**File Python dự kiến:** `ingestion/raw/manifest.py`. **Output runtime dự kiến:** `manifest.json` và `schema.json` dưới prefix của từng table batch trên MinIO. Helper dưới đây chỉ mô tả một file; phần gom metadata thành manifest và ghi schema JSON chưa được viết.

**Đầu vào → đầu ra:** đường dẫn Parquet local + object key tương ứng → dictionary metadata của file. Hàm không upload, không sửa Parquet và không xác minh object remote. `object_key` là đường dẫn bên trong bucket, không phải URL `s3://...`.

Hàm sau nhận file Parquet local từ đúng batch và object key đích. Implementation phải lấy danh sách file từ load package của dlt, loại system tables, rồi kiểm tra đúng table/batch prefix; không glob toàn bucket.

```python
# File dự kiến: ingestion/raw/manifest.py
# Vai trò: tạo metadata từng payload để bước commit đối soát và reader truy vết.
import hashlib
from pathlib import Path

import pyarrow.parquet as pq


def describe_parquet(path: Path, object_key: str):
    """Tính checksum, byte size, row count và fingerprint schema một Parquet.

    Caller bảo đảm file không đổi trong suốt quá trình đọc và thuộc đúng batch.
    """
    digest = hashlib.sha256()
    # Hash theo chunks 1 MiB, không giữ toàn bộ file trong RAM.
    # iter(callable, b"") dừng khi stream.read() trả bytes rỗng ở cuối file.
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    # Đọc footer/schema để lấy metadata; chưa scan mọi page dữ liệu trong file.
    # Remote validator vẫn phải kiểm tra khả năng đọc payload theo contract.
    parquet = pq.ParquetFile(path)
    schema_bytes = parquet.schema_arrow.serialize().to_pybytes()
    # Hai hash có mục đích khác nhau:
    # sha256 kiểm nội dung file; arrow_schema_sha256 kiểm biểu diễn schema Arrow.
    return {
        "object_key": object_key,
        "byte_size": path.stat().st_size,
        "row_count": parquet.metadata.num_rows,
        "sha256": digest.hexdigest(),
        "arrow_schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
    }
```

File phải bất biến trong lúc describe/upload; sau upload phải đọc lại object để kiểm chứng checksum/metadata, không coi S3 ETag luôn là SHA-256. Arrow schema fingerprint cần cùng version/canonicalization khi so sánh qua các môi trường. `schema.json` lưu type/precision/scale/nullability đã kiểm tra; không chỉ lưu hash mà bỏ mô tả schema.

JSON sau là **shape minh họa**, các giá trị trong `<...>` chưa được tính bởi pipeline:

**Vị trí output dự kiến:** `s3://<bucket>/raw/e_commerce/product/extract_date=<YYYY-MM-DD>/batch_id=<uuid>/manifest.json`. Trong JSON, `<batch-prefix>` là `raw/e_commerce/product/extract_date=<YYYY-MM-DD>/batch_id=<uuid>` — không bao gồm tên bucket. JSON chuẩn không hỗ trợ comments, vì vậy tên output và giải thích trường đặt ngoài code block.

```json
{
  "batch_id": "<uuid-duoc-caller-chot>",
  "run_id": "<execution-id>",
  "source_snapshot_id": "<bootstrap-snapshot-set-fingerprint>",
  "table": "product",
  "mode": "snapshot",
  "schema_version": "raw-v1",
  "extracted_at_utc": "<UTC timestamp cua lan extract goc>",
  "cursor_start": null,
  "cursor_end": null,
  "overlap": null,
  "schema_object_key": "<batch-prefix>/schema.json",
  "schema_hash": "<sha256-cua-schema-json-canonical>",
  "row_count": 28356,
  "files": [
    {
      "object_key": "<batch-prefix>/<load-id>.<file-id>.parquet",
      "row_count": 28356,
      "byte_size": "<so-byte-thuc-te-kieu-integer>",
      "sha256": "<sha256-payload-parquet>",
      "arrow_schema_sha256": "<arrow-schema-fingerprint>"
    }
  ]
}
```

`row_count` là tổng của toàn bộ files. Ví dụ đặt một file để dễ đọc, không giả định dlt luôn tạo đúng một file mỗi bảng. Khi retry, dùng lại metadata extract gốc; không đổi `extracted_at_utc` khiến manifest đã tồn tại bị khác payload. Sau khi cả 4 table batches committed, ghi snapshot-set manifest trỏ tới chúng và commit marker riêng của set.

| Trường manifest | Ý nghĩa / nguồn giá trị |
| --- | --- |
| `batch_id`, `run_id` | Batch dữ liệu và execution gắn với lần extract; retry commit phải dùng lại manifest gốc. Attempt retry có thể log riêng, không sửa manifest đã commit. |
| `source_snapshot_id` | Fingerprint bộ 4 CSV bootstrap để truy vết nguồn ban đầu; không tự chứng minh DB chưa bị cập nhật sau bootstrap. |
| `table`, `mode` | Bảng nguồn và chiến lược load; mẫu hiện là full snapshot. |
| `schema_version` | Phiên bản contract raw do dự án quản lý, khác hash schema cụ thể. |
| `extracted_at_utc` | Timestamp extract được caller ghi nhận; không lấy thời điểm retry commit thay thế. |
| `cursor_start`, `cursor_end`, `overlap` | Dành cho incremental sau này; snapshot hiện để null. |
| `schema_object_key`, `schema_hash` | Vị trí schema JSON và checksum bytes theo quy ước serialize đã chốt. |
| `files` | Danh sách chính xác payload của table batch; không bao gồm system tables của dlt hoặc file từ batch khác. |
| `row_count` cấp manifest | Tổng rows các file, đối soát với nguồn đã chốt ở thời điểm snapshot. |
| `files[].byte_size` | Số bytes thực tế dạng integer khi chạy thật; chuỗi `<...>` hiện chỉ là placeholder. |

### 6.5. Commit metadata và marker sau cùng

**File dự kiến:** `ingestion/raw/commit.py`. Hai hàm trong block dưới cùng thuộc file này: `put_once` là helper ghi object có điều kiện; `commit_table_batch` điều phối validate → ghi manifest → ghi marker.

**Đầu vào → đầu ra:** S3 client đã cấu hình, bucket, prefix, manifest và hàm validator → ghi `manifest.json`/`_SUCCESS`, hoặc raise exception. Hai hàm không có giá trị return tường minh. `s3` dự kiến là boto3 S3 client do caller tạo với endpoint/credentials MinIO; các biến cấu hình dlt ở 6.3 không tự cấu hình client boto3 này.

Ví dụ dùng conditional PUT cho metadata write-once. `IfNoneMatch="*"` phải được kiểm tra với boto3/botocore và phiên bản MinIO thực tế khi integration; đây chưa phải bằng chứng target hỗ trợ mọi conditional-write semantics.

```python
# File dự kiến: ingestion/raw/commit.py
# Vai trò: chỉ công bố table batch sau khi payload đã được validator xác minh.
import hashlib
import json

from botocore.exceptions import ClientError


def put_once(s3, bucket: str, key: str, payload: bytes, content_type: str):
    """Ghi object mới; nếu đã tồn tại thì chỉ chấp nhận bytes giống hệt.

    Yêu cầu target hỗ trợ conditional PUT; đây chưa phải object-lock policy.
    """
    try:
        # IfNoneMatch='*': chỉ tạo nếu key chưa tồn tại, tránh check-then-write
        # bằng HEAD rồi PUT vốn có khoảng trống cho hai writers cùng ghi.
        s3.put_object(
            Bucket=bucket, Key=key, Body=payload,
            ContentType=content_type, IfNoneMatch="*",
        )
    except ClientError as exc:
        # 412: điều kiện không thỏa do object tồn tại; cần đọc để so sánh.
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
            # 409/network errors phải đi qua retry policy, không coi là success.
            raise
        # Retry cùng payload được xem là hoàn tất; khác payload phải báo conflict.
        # with đóng response body sau khi đọc để trả kết nối về client pool.
        response = s3.get_object(Bucket=bucket, Key=key)
        with response["Body"] as body:
            existing = body.read()
        if existing != payload:
            raise RuntimeError("Immutable raw metadata conflict") from exc


def commit_table_batch(s3, bucket, prefix, manifest, verify_payloads):
    """Validate payload remote rồi publish manifest và marker của một bảng.

    prefix là object-key prefix, không gồm bucket/s3://.
    Đây chưa phải commit snapshot-set đủ 4 bảng.
    """
    # Callback bắt buộc: đọc remote files/schema và fail nếu không đúng contract.
    # Không truyền một callback rỗng khi implementation.
    verify_payloads(s3, bucket, prefix, manifest)
    # Serialize ổn định cho cùng nội dung: sắp keys, bỏ whitespace thừa,
    # encode UTF-8. Thứ tự list files vẫn phải được caller chuẩn hóa/giữ ổn định.
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    prefix = prefix.rstrip("/")  # Tránh tạo double slash khi ghép object key.
    # Bước 1: ghi manifest. Nếu crash sau đây, reader vẫn chưa nhận batch
    # vì thiếu marker. Retry cùng bytes có thể đi tiếp mà không overwrite.
    put_once(s3, bucket, f"{prefix}/manifest.json", manifest_bytes, "application/json")
    # Bước 2: marker chứa SHA-256 của CHÍNH bytes manifest vừa serialize.
    # Đây không phải checksum một Parquet; checksum Parquet nằm trong files[].
    marker = hashlib.sha256(manifest_bytes).hexdigest().encode("ascii")
    # Marker luôn ghi cuối cùng. Hai PUT không tạo thành transaction S3;
    # tính nhất quán còn phụ thuộc payload bất biến và protocol reader/writer.
    put_once(s3, bucket, f"{prefix}/_SUCCESS", marker, "text/plain")
```

`verify_payloads` chưa được triển khai trong tài liệu. Contract của callback: mọi key thuộc đúng table/batch, file và schema tồn tại, byte count/checksum đúng, Parquet đọc được và tổng rows khớp nguồn đã chốt; validate cả trường hợp zero-row tables. Caller còn cần single-writer/ownership cho batch prefix và cấm extract/upload tiếp sau commit. Conditional PUT cho marker **không tự làm Parquet objects immutable**.

Reader downstream yêu cầu cả manifest và marker, kiểm tra SHA-256 trong `_SUCCESS` khớp bytes manifest trước khi đọc payload. Commit marker cấp ứng dụng này độc lập với `_dlt_loads`/pipeline state của dlt. Dùng [boto3 PutObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html) và error handling thực tế khi tích hợp.

### 6.6. Cách ghép các ví dụ

**File điều phối dự kiến:** `ingestion/cli.py` cho validate/extract/commit; `scripts/bootstrap/load_csv.py` cho bootstrap. Sơ đồ sau là thứ tự thực thi, không phải script đã có thể chạy. CLI ingestion sẽ là entrypoint dùng chung khi chạy thủ công và khi Airflow gọi.

```text
# Sơ đồ gọi file dự kiến — không phải nội dung executable của một file Python.
csv_contracts.py: validate 4 CSV + compute snapshot-set fingerprint [còn bổ sung]
    → scripts/bootstrap/load_csv.py: bootstrap 4 bảng trong transaction
    → freeze simulator writes trong lúc extract/đối soát initial snapshot
    → lock batch + inspect marker để skip/resume
    → ingestion/sources/postgres.py: extract_snapshot(batch_id, extract_date)
    → collect dlt files [còn bổ sung]
    → ingestion/raw/manifest.py: describe files + build manifest/schema [còn bổ sung]
    → ingestion/raw/commit.py: commit_table_batch(...) gọi remote validator
    → commit snapshot-set manifest + marker
    → release locks; trả manifest URI và counts, không trả records qua XCom
```

**Ví dụ nối hàm ở mức ý tưởng:** bootstrap gọi `read_checked_csv(path, "product")`, nhận `(records, inventory)` rồi truyền vào `bootstrap_product(records, inventory)`. Sau khi đủ 4 bảng đã bootstrap và nguồn ổn định, ingestion mới gọi `extract_snapshot(batch_id, extract_date)`. Không truyền `records` CSV vào dlt vì nguồn extract lúc này là Postgres.

| Phần còn thiếu | Vị trí dự kiến | Lý do cần trước khi chạy thật |
| --- | --- | --- |
| CLI, validate arguments, batch ownership và retry | `ingestion/cli.py` | Chốt input run, giữ lock, xử lý trạng thái thành công/dở dang; gọi các module đúng thứ tự. |
| Parse kiểu, FK và snapshot-set fingerprint | `ingestion/sources/csv_contracts.py` | Mẫu mới kiểm cấu trúc/khóa từng file; chưa đủ contract cho 4 bảng. |
| DDL đủ 4 bảng và quyền nguồn | `infra/postgres/init/001_source_schema.sql` và migrations sau này | Mẫu SQL hiện chỉ có product và ledger. |
| Bootstrap 4 bảng chung transaction | `scripts/bootstrap/load_csv.py` | Tránh nguồn chỉ mới nạp một phần khi có lỗi. |
| Thu thập dlt payloads và metadata/schema | `ingestion/raw/manifest.py` | `describe_parquet` chưa tìm files từ load package và chưa tạo manifest hoàn chỉnh. Nếu file local đã bị dlt dọn, cần staging/đọc remote theo thiết kế được kiểm chứng. |
| Remote validator | `ingestion/raw/validation.py` | Hiện chỉ truyền callback `verify_payloads`; cần kiểm files/schema/count/checksum thực tế. |
| Snapshot-set commit | `ingestion/raw/commit.py` | Marker một bảng chưa đủ công bố bộ snapshot nhất quán gồm cả 4 bảng. |
| Tạo S3 client riêng cho commit/validation | `ingestion/cli.py` hoặc module cấu hình dùng chung | Truyền endpoint và credentials cho boto3, không mặc định dùng namespace env của dlt. |

Phần cần làm trước khi chuyển thành CLI: parse schema typed cho 4 bảng, DB migrations/permissions, snapshot consistency, file collection từ dlt load packages, remote validator, batch ownership/retry recovery, snapshot-set commit, Docker config và các integration tests ở mục 3.E. Chưa chạy bất cứ snippet nào có kết nối Postgres/MinIO hay thay đổi CSV gốc.
