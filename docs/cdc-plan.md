# OLTP và CDC · chặng mở rộng

> Thiết kế tùy chọn sau snapshot/insight. Chưa chọn connector, bật logical decoding, tạo publication/slot hoặc cấp role replication.

## 1. OLTP lab trước

CSV seed PostgreSQL một lần. Thêm script giao dịch có transaction, PK/FK và test cases: insert order/line, sửa profit/sales của đơn cũ, đổi dimension, delete line. Giữ dữ liệu synthetic/test tách khỏi baseline báo cáo. Không chạy lại bootstrap để reset nguồn mỗi refresh.

Có thể thử batch incremental theo updated_at trước: phải giải quyết ties/cursor, update đơn cũ và soft-delete/tombstone. Đây là incremental polling, không gọi là log-based CDC. order_date không phải change cursor.

## 2. CDC thực sự

Luồng mục tiêu: PostgreSQL WAL/logical decoding → connector/consumer → change journal local bền vững → DuckDB Bronze → dbt → Gold release.

Consumer/connector chọn sau PoC; không giả định Debezium có sẵn sink DuckDB trực tiếp, không mặc định phải dựng Kafka. Journal có thể dùng files local theo batch nếu protocol commit/checkpoint đã kiểm chứng; không cần MinIO trong lab này.

Các contract bắt buộc:
- Initial snapshot và vị trí WAL phải nối liên tục, không gap.
- Event có PK, operation, transaction/commit order và vị trí LSN; delete phải có key đủ apply.
- Apply đúng commit order; có cách dedup replay khi crash; cursor/checkpoint chỉ tiến sau apply bền vững. Không hứa exactly-once end-to-end.
- DuckDB chỉ một writer; consumer buffer/commit batch, không ghi cạnh tranh với dbt.
- Model downstream phản ánh sửa/xóa đơn cũ; bắt đầu full dbt rebuild thay vì incremental mart quá sớm.
- Theo dõi lag, retained WAL, journal disk usage và retention/recovery.

PostgreSQL logical slots có thể phát lại sau crash và giữ WAL khi consumer chậm/dừng. Vì vậy CDC thêm nghĩa vụ vận hành dung lượng, dù không có MinIO. [PostgreSQL logical decoding](https://www.postgresql.org/docs/16/logicaldecoding-explanation.html).

## 3. Ranh giới platform

Trước PoC phải kiểm tra wal_level, quyền replication, slot/publication scope, replica identity và giới hạn WAL. Không tự thay config/restart PostgreSQL chung, không cấp quyền replication cho extractor thông thường.

Connector thường trực cần đăng ký idle RAM/CPU và audit lại toàn platform; không coi ngân sách task refresh là ngân sách cho daemon CDC. Thay đổi shared service/policy chỉ ở window đã drain, bảo toàn các database/slot dự án khác.

## 4. Nghiệm thu

Chứng minh insert/update/delete đúng; crash trước/sau checkpoint không mất hoặc nhân đôi dữ liệu; catch-up khi consumer dừng; sửa đơn cũ cập nhật RFM/monthly/basket; rebuild từ snapshot+journal đạt cùng metric. Chỉ làm sau khi pipeline snapshot và báo cáo insight đã ổn định.
