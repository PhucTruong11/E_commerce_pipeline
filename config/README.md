# Cấu hình runtime dự kiến

Thư mục dành cho mẫu env và dbt profile riêng của e-commerce. Chưa có config sử dụng được.

Khi triển khai sẽ thêm .env.example và profiles.example.yml với placeholders: PostgreSQL ecom_source_dev, owner/reader riêng, input paths, DuckDB candidate/release paths và analysis parameters. dbt dùng adapter dbt-duckdb; PostgreSQL là nguồn.

Env/profile thật và passwords không commit hoặc copy vào image. Không dùng config volume/admin credentials của LaplapTech. Xem [Docker plan](../docs/docker-plan.md).
