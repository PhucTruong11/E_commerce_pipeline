# Plan nhỏ · kiểm Bronze và bắt đầu Silver

> Ngày 2026-10-24. Đây là kế hoạch + mẫu SQL, **chưa tạo/chạy models**. Mục tiêu học source(), ref(), staging views, LEFT JOIN và quality tests; chưa làm Gold/insight ở bước này.

## 1. Bronze: mô tả và kiểm tra phần đã nạp

Bronze đã được Python extract từ PostgreSQL vào một candidate DuckDB: 4 bảng, 100.889 dòng baseline, có reconciliation và extraction lineage. dbt chỉ khai báo/kiểm thử nguồn, không load hoặc tạo lại Bronze.

| Bảng | Grain / khóa | Baseline rows |
| --- | --- | ---: |
| bronze.customer | Một customer_id | 17.415 |
| bronze.product | Một product_code | 28.356 |
| bronze.region | Một region_code | 3.828 |
| bronze.ecom_sales | Một row_id, chưa phải một order | 51.290 |

**Việc làm tiếp:** bổ sung mô tả columns và unique/not_null cho 4 khóa vào **dbt/models/bronze/sources.yml**. Kiểm tra _extraction_id/_extracted_at/_source_table và đối chiếu receipt của đúng candidate. Không hardcode row count baseline làm chuẩn cho mọi snapshot tương lai; không tính freshness từ order_date của dataset lịch sử.

Mẫu fragment cho bảng product trong sources.yml hiện có; merge vào table entry tương ứng, không khai báo thêm một source bronze trùng tên:

```yaml
- name: product
  columns:
    - name: product_code
      description: Source product code; business SKU identity remains open.
      data_tests: [unique, not_null]
```

Giữ nguyên business values và precision trong Bronze. Baseline có 2 dòng sales orphan product và 2 orphan region; các tập có thể chồng nhau. Giữ/report chúng, không dùng inner join hoặc relationships test nghiêm ngặt để vô tình loại sales trước khi chốt unknown policy.

## 2. Silver bước đầu: hai staging views

Bronze đã có kiểu date/numeric rõ. Silver tập trung naming, quy tắc null cho nhãn và giữ grain; không cast tiền sang float, không tự trim/gộp mã định danh hoặc dedup tùy ý.

File dự kiến **dbt/models/silver/stg_ecom_sales.sql**:

```sql
-- Một row_id; giữ nguyên keys, tài chính và lineage.
SELECT
    row_id, order_id, order_date,
    customer_id, segment, region_code, product_code,
    quantity, sales, discount, profit,
    _extraction_id, _extracted_at, _source_table
FROM {{ source('bronze', 'ecom_sales') }}
```

File dự kiến **dbt/models/silver/stg_products.sql**:

```sql
-- Một product_code. Chỉ chuẩn hóa nhãn; không thay business key.
SELECT
    product_code,
    NULLIF(TRIM(product), '') AS product_name,
    NULLIF(TRIM(category), '') AS category,
    NULLIF(TRIM(subcategory), '') AS subcategory,
    _extraction_id, _extracted_at, _source_table
FROM {{ source('bronze', 'product') }}
```

Hai models dùng materialized=view và physical schema silver theo dbt_project.yml/macro hiện có. Thêm **dbt/models/silver/schema.yml** để mô tả grain và kiểm unique/not_null của row_id, product_code; order_id không phải khóa unique của sales lines.

## 3. Nếu còn thời gian: một join có kiểm soát

File dự kiến **dbt/models/silver/int_order_lines_enriched.sql**:

```sql
-- LEFT JOIN bảo toàn sales; không biến product không khớp thành dòng bị mất.
SELECT
    sales.*,
    products.product_name,
    products.category,
    products.subcategory,
    products.product_code IS NULL AS is_unknown_product
FROM {{ ref('stg_ecom_sales') }} AS sales
LEFT JOIN {{ ref('stg_products') }} AS products
    ON sales.product_code = products.product_code
```

Giữ mã product nguồn ngay cả khi không match; chưa tự tạo dimension member giả. is_unknown_product phản ánh lookup không khớp, khác việc product_name của một product hợp lệ bị null.

Region/customer staging và enrichment làm ở lượt sau; lúc này chưa có region unknown flag trong model mẫu. Hai orphan region vẫn nằm nguyên trong sales và receipt. Chưa roll-up orders, chốt order key, tính RFM hoặc diễn giải sales là gross/net.

## 4. Checkpoint cần đạt khi triển khai

| Kiểm tra | Điều kiện |
| --- | --- |
| Source/model keys | Unique/not-null tại đúng grain |
| Staging sales | Cùng row_id set, count, quantity/sales/profit totals và null counts với Bronze của cùng extraction |
| Staging products | Giữ đúng product_code set/count; thay đổi nhãn phải đúng quy tắc đã ghi |
| Sau LEFT JOIN | Count/row_id/totals không đổi; không fan-out; key và lineage nguồn không đổi |
| Orphan product | Baseline hiện tại có 2 sales rows được flag, không drop; lần sau đối chiếu receipt mới |
| Semantic | Ghi các câu hỏi còn mở về currency, discount scale và ý nghĩa sales/profit |

Tests dự kiến đặt tại **dbt/tests/**: đối soát line keys/counts, nulls/totals và orphan flag. Không áp range discount hoặc enum nghiệp vụ trước khi profiling. Mẫu là plan, các tests chưa tồn tại/chưa pass.

## 5. Thứ tự thực hành

1. Chọn candidate đã có receipt validated_bronze; kiểm đúng extraction_id. Không chạy dbt trên bản inspection trong .local/datagrip.
2. Bổ sung Bronze source tests, rồi hai staging views + schema.yml.
3. Thêm đường chạy build/test có guard vào scripts/Invoke-Dev.ps1 và scripts/environment.py khi implementation: đúng ECOM_DUCKDB_PATH, resource budget và writer lock; đóng loader connection trước dbt. Wrapper hiện chưa có action build models.
4. Chạy source tests và build hai staging views trên candidate, lưu dbt artifacts theo run; đối soát rồi mới thử join optional.
5. Ghi kết quả thực tế; chỉ sau đó mới mở rộng 4 staging models, order grain và Gold.

Các lệnh dbt mục tiêu bên trong runtime sau khi đường chạy có guard được triển khai; **chưa chạy trực tiếp trong scaffold hiện tại**:

```text
dbt test --project-dir /app/dbt --profiles-dir /app/config --select source:bronze
dbt build --project-dir /app/dbt --profiles-dir /app/config --select stg_ecom_sales stg_products
```

Manual runtime vẫn phải theo shared resource policy/window; không bypass pool, tăng memory hoặc restart shared services để chạy thử models. Chưa publish Gold, chưa có serving release hoặc DAG; DataGrip inspection copy không tự cập nhật sau build/extract.

**Hoàn thành mốc nhỏ:** Bronze source tests đạt + hai staging views giữ đúng grain/keys/totals. Join chỉ tính hoàn thành khi đối soát và unknown flags đạt. Tài liệu này không đánh dấu các bước đó đã chạy.

Tham khảo: [dbt sources](https://docs.getdbt.com/docs/build/sources), [dbt data tests](https://docs.getdbt.com/docs/build/data-tests). Kiến trúc/schema theo [architecture](../architecture.md), grain/metric theo [data modeling](../data-modeling.md).
