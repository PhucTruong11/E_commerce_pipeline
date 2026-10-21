# Operations và recovery

> Runbook mục tiêu. Các thao tác mô tả dưới đây chưa có CLI/script tương ứng.

## Các chế độ chạy

| Chế độ | Đọc từ | Ghi vào | Điều kiện |
| --- | --- | --- | --- |
| Initial load | Snapshot nguồn được cho phép | Postgres mô phỏng, rồi raw và build warehouse | Schema và khóa đã profiling |
| Scheduled batch | Postgres local | Raw → Bronze → Silver → Gold | Một writer; boundary extract rõ ràng |
| Retry downstream | Raw committed | Build warehouse | Giữ batch IDs và ledger; không bắt buộc nguồn online |
| Replay | Manifest set được chọn | Warehouse mới, ledger mới | Snapshot nền + changes + schema; cùng as-of |
| Backfill | Raw hoặc source theo contract riêng | Build target riêng | Không sửa checkpoint scheduled ingestion |
| Rollback serving | Release trước đó | Pointer serving | Release cũ còn nguyên và đã qua gate |

## Failure modes

| Tình huống | Hành vi yêu cầu |
| --- | --- |
| Extract fail trước `_SUCCESS` | Batch chưa committed bị bỏ qua; retry có batch mới hoặc hoàn tất theo protocol |
| Raw commit xong nhưng checkpoint chưa ghi | Có thể extract trùng; phiên bản/khóa downstream ngăn double counting |
| Loader fail giữa transaction | Rollback cả data và ledger; retry cùng manifest |
| Cùng key/version nhưng payload khác | Fail/quarantine, giữ raw, cần giải quyết conflict |
| dbt model hoặc quality test fail | Dừng publish; tiếp tục phục vụ release trước |
| Schema thay đổi không tương thích | Dừng batch; giữ raw và báo schema diff; không silently cast mất dữ liệu |
| Publisher fail trước pointer switch | Release mới chưa có người dùng; release trước vẫn active |
| Dashboard đọc lỗi sau chuyển release | Đóng/mở lại connection; rollback pointer nếu release không dùng được |

## Dựng lại warehouse từ raw

1. Chọn release chuẩn, đọc danh sách raw batches và `as_of_date` trong metadata.
2. Kiểm tra MinIO có đủ manifest, schema, checksum và commit markers.
3. Dừng quyền ghi vào target rebuild; tạo file warehouse mới và ledger trống.
4. Apply snapshot nền, dimension snapshots đã chọn và sales changes theo version.
5. Chạy dbt build cùng phiên bản code/config của release chuẩn.
6. So sánh tập khóa, counts và tổng sales/profit cùng RFM/basket mẫu; sai số tài chính theo precision đã xác nhận.
7. Publish thành release mới nếu gate đạt. Không tự xóa release cũ hoặc raw để dọn dẹp.

Kịch bản nghiệm thu phải thực hiện khi Postgres nguồn tắt để chứng minh không có read-through âm thầm về nguồn.

## Metadata và quan sát

Theo dõi `run_id`, `batch_id`, source cursor range, extracted/applied row counts, inserted/updated/unchanged rows, duplicates/conflicts, missing dimension rate, durations và test status. Serving hiển thị release và kỳ dữ liệu.

Phân biệt source-data recency với pipeline freshness. Dataset lịch sử không tự nhiên bị coi là pipeline lỗi chỉ vì `MAX(order_date)` xa hiện tại. MVP có thể kiểm tra extract/publish time, còn kỳ dữ liệu phải được hiển thị riêng.

## Acceptance scenarios

| Kịch bản | Kết quả cần chứng minh |
| --- | --- |
| Apply cùng batch hai lần | Count/keys/sales/profit không đổi |
| Hai batches chứa cùng key/version | Không double count; payload conflict bị chặn |
| Sửa sales/profit của đơn cũ | Facts và các aggregates/customer marts liên quan cập nhật |
| Product dimension có hai dòng cùng code | Không fan-out; conflict bị phát hiện |
| SKU lặp nhiều dòng trong một đơn | Basket chỉ tính một lần cho sản phẩm đó trong đơn |
| Thiếu tháng năm trước | YoY không so nhầm tháng; trả baseline missing |
| Replay khi nguồn tắt | Warehouse dựng được và đối soát bằng release chuẩn |
| Thêm dữ liệu invalid có chủ đích | Publish bị chặn, người dùng tiếp tục đọc release trước |
| Hai run khởi động cùng lúc | Airflow pool + file lock chỉ cho một writer; lock giữ tới hết publish |

## Lưu trữ và quyền

`data/` dành cho runtime artifacts local. Volumes Postgres/MinIO/Airflow được khai báo khi viết Compose; không commit dữ liệu thật. Airflow metadata DB và source DB tách riêng; reset demo không được tác động Airflow hiện có. Raw archive và metadata/state cần được bảo vệ cùng nhau; lake local đơn máy không tự là disaster recovery backup. Retention và backup sang nơi độc lập là quyết định vận hành cần bổ sung trước khi có dữ liệu quan trọng.

## Hai chế độ Docker

Xem [Airflow & Docker](airflow-docker.md). Ở chế độ tích hợp, chỉ deploy DAG/runtime của dự án vào Airflow hiện có sau khi xác nhận compatibility; không khởi tạo hay migrate metadata DB hiện có bằng cấu hình standalone. Standalone dùng Compose project/network/volumes và host ports riêng để tránh đụng stack cũ.
