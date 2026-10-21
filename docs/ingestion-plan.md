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
