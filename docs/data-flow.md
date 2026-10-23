# Data flow và contract nguồn / warehouse

> Plan mới: PostgreSQL nguồn, DuckDB analytics, dbt Core + dbt-duckdb. Chưa triển khai.

![Data flow](diagrams/data-flow.svg)

## 1. CSV → PostgreSQL bootstrap

Validate đủ 4 CSV, schema/type/keys/FK, giữ bytes gốc và checksum. Bootstrap cả 4 nguồn trong một transaction vào e_commerce và ghi bootstrap_id/inventory. Sau initial load, cùng CSV thì skip bootstrap; không ghi đè các giao dịch được tạo sau đó. CSV khác phải qua explicit reset/new-baseline, không tự replace nguồn.

## 2. PostgreSQL → candidate DuckDB

Extractor dùng ecom_reader, kiểm tra đúng database/user, mở một REPEATABLE READ READ ONLY transaction cho cả 4 bảng. Đọc theo batch, giữ consistency khi nguồn có thay đổi đồng thời.

Tạo candidate file mới cho mỗi extraction_id. Nạp bronze.ecom_sales/customer/product/region với metadata extraction_id, source table và extracted_at. Kiểm tra row count, keys và tổng tiền cùng snapshot nguồn; lỗi thì candidate không được phục vụ.

Không dùng checksum CSV làm identity của snapshot PG sau khi OLTP thay đổi. bootstrap_id nhận diện đầu vào ban đầu; extraction_id nhận diện lần đọc nguồn; analysis_run_id gắn code/parameters/tests; release_id nhận diện Gold đã duyệt.

## 3. dbt và insight

Đóng writer DuckDB của loader trước khi gọi dbt. dbt target là candidate path cố định; không query PG trực tiếp trong models. Bronze → staging → intermediate → marts, full rebuild ban đầu.

Giữ grain row_id cho lines, order_key đã kiểm chứng cho orders. Reconcile totals và tests nghiệp vụ trước khi xuất SQL/report. Cùng source nhưng SQL thay đổi vẫn build lại.

## 4. Publish

Xuất chỉ Gold được phép sang release file mới; loại raw/PII. Đóng mọi writer, mở read-only để kiểm tra. Metadata gồm extraction_id, code revision/hash, as_of_date, test status và release_id.

Atomic switch active pointer trên cùng filesystem sau khi pass; giữ release cũ để rollback. Readers không mở build file; chọn một immutable release cho toàn request. dbt build không phải transaction toàn pipeline, nên candidate/pointer là ranh giới publication.

## 5. Retry và restore

Full snapshot retry dựng candidate mới, không append vào serving. Trước pointer switch thất bại thì release cũ vẫn active. Khi mất build, lấy lại nguồn hiện hành; muốn khôi phục đúng lịch sử phải còn build/raw snapshot hoặc PG backup/change journal của thời điểm đó.

CDC là chặng sau: [CDC plan](cdc-plan.md). Không dùng watermark giả cho CSV tĩnh và không coi source snapshot là lịch sử thay đổi.
