# Roadmap triển khai

> Chưa bắt đầu implementation pipeline. Đã có 4 CSV local và kiểm tra sơ bộ ngày 2026-10-21; xem [ingestion plan](ingestion-plan.md). Bốn chặng là thứ tự ưu tiên, không cam kết mỗi chặng đúng một tuần.

## Chặng 1 · Source, profiling và raw

- [x] Có 4 CSV local trong `data/bootstrap/`; chặn khỏi Git/Docker build context. Điều kiện phân phối dataset vẫn cần xác nhận trước khi chia sẻ dữ liệu.
- [ ] Profiling khóa, duplicate, null, date range, precision, enum và join cardinality của 4 bảng.
- [ ] Chốt metric contract còn mở trong `context.md`.
- [ ] Xác nhận Airflow hiện có: phiên bản, executor, DAG folder, Compose network và volume. Không tự thay đổi stack đang dùng.
- [ ] Tạo image runtime và cấu hình services Postgres/MinIO để tích hợp Airflow hiện có; persistent volumes, health checks, secrets example.
- [ ] Thiết kế standalone Compose với Airflow + metadata DB riêng cho người clone repo.
- [ ] Ghim dependency versions và kiểm tra tổ hợp Airflow / dlt / dbt-duckdb; cách ly dbt dependencies bằng venv trong image.
- [ ] Bootstrap snapshot; simulator insert/update với metadata nguồn.
- [ ] dlt extract và commit raw Parquet bằng manifest + marker.

**Hoàn thành khi:** đọc lại batch theo manifest khớp count/checksum; không đọc batch dở dang; có báo cáo profiling và chiến lược khóa được ghi nhận.

## Chặng 2 · Bronze, dbt và business answers

- [ ] Viết loader snapshot/incremental, ledger và transaction.
- [ ] Tạo dbt project/profile example, source definitions, staging/intermediate/core models.
- [ ] Xây marts theo nhu cầu Q01–Q15; viết SQL analyses với định nghĩa rõ ràng.
- [ ] Thêm tests cho uniqueness, relationships, fan-out, roll-up và financial totals.
- [ ] RFM deterministic với as-of; basket distinct theo đơn; YoY không bỏ tháng khuyết.

**Hoàn thành khi:** chạy lại cùng input không nhân bản; đơn cũ được sửa phản ánh đúng downstream; 15 câu hỏi có SQL và output có thể truy vết. Nếu câu hỏi chưa đủ semantic phải ghi blocker cụ thể.

## Chặng 3 · Orchestration, recovery và CI

- [ ] DAG mỏng: extract → commit raw → build_and_publish; task cuối giữ lock qua load Bronze, dbt, quality gate và publish.
- [ ] Airflow pool một slot cho writer, `max_active_runs=1`, file lock và retry đúng manifest set.
- [ ] Kiểm tra DAG import trên đúng phiên bản Airflow; không truy cập network/DB ở parse time.
- [ ] Ghi batch IDs, row counts, cursor, duration và gate status vào metadata.
- [ ] Publish release riêng và pointer; giữ release cũ khi lỗi.
- [ ] GitHub Actions dùng fixtures giả lập, chạy kiểm tra Python/SQL và dbt build.
- [ ] Đóng gói custom Airflow/runtime image và dashboard image; standalone Compose có init/migration, health checks, volumes và sample config.
- [ ] Chạy smoke test hai chế độ: Airflow có sẵn và standalone từ checkout mới. Dataset demo dùng fixtures giả lập, không yêu cầu tài khoản Xóm Data; chế độ dữ liệu thật dùng snapshot/credentials hợp lệ.
- [ ] Thêm lệnh tiện ích sau khi implementation tồn tại; README chỉ ghi lệnh đã chạy kiểm chứng.
- [ ] Replay/backfill vào warehouse mới; failure-injection scenarios.

**Hoàn thành khi:** cố tình fail giữa load có thể retry; crash sau raw commit không làm mất dữ liệu; Postgres tắt vẫn rebuild được; invalid Gold không tới serving.

Không dùng Slim CI ở chặng đầu nếu chưa có baseline manifest và cơ chế defer/state được kiểm chứng. Chạy dbt build trên fixture đầy đủ trước.

## Chặng 4 · Serving và Text-to-SQL

- [ ] Streamlit đọc release đã publish và hiển thị data period/release ID.
- [ ] Dashboard giải quyết các câu hỏi chính về profitability, discount, thị trường và khách hàng.
- [ ] Gold schema context lấy từ dbt docs/manifest cùng metric definitions đã duyệt.
- [ ] Gemini model ID cấu hình được; xác nhận pricing/availability tại lúc tích hợp.
- [ ] SQLGlot allowlist cùng executor sandbox và resource limits.
- [ ] Tạo tập câu hỏi Anh/Việt có SQL/result kỳ vọng; kiểm tra tính đúng và từ chối truy vấn không được phép.
- [ ] README có hướng dẫn chạy thật, ảnh UI và kết quả đo đã xác minh.

**Hoàn thành khi:** người đọc sử dụng release ổn định; Text-to-SQL trả SQL và lineage, vượt qua kiểm tra correctness/security; không công khai PII hoặc secrets.

## Backlog sau MVP

Cosmos để hiển thị lineage dbt chi tiết trong Airflow, log-based CDC, tombstone/hard delete, SCD2 khi có lịch sử thay đổi đáng tin, cloud warehouse, transactional lake format, incremental dbt tối ưu và phân tích churn được kiểm định. Cosmos chỉ bật sau khi xác nhận version compatibility và thiết kế locking/run isolation khi tách nhiều model tasks. Chỉ thêm khi có nhu cầu/tiêu chí đo cụ thể.
