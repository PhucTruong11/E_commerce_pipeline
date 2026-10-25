# Plan raw → Gold · contracts, clean, macros và tests

> Cập nhật 25/10/2026. Plan kỹ thuật duy nhất, đi cùng [business-questions.md](business-questions.md). File này gộp bootstrap/extraction, thực hành Bronze/Silver và review Bronze cũ. **Bản cập nhật này chỉ thay tài liệu**, không chạy lại ingestion/dbt hoặc triển khai Silver/Gold.

Đọc theo thứ tự: [trạng thái](#status) → [yêu cầu](#requirements) → [raw](#raw) → [Bronze](#bronze) → [macros](#macros) → [Silver](#silver) → [Gold](#gold) → [test matrix](#tests) → [cách chạy/checkpoint](#run). [Evidence](#evidence) giữ các kết quả ngày 24/10/2026.

<a id="status"></a>
## 1. Hiện trạng và flow

```text
4 CSV → Python bootstrap một lần → PostgreSQL e_commerce.*
                                      ↓ Python full consistent snapshot
                                DuckDB raw.*
                                      ↓ source('raw', ...)
                                bronze.bronze_*       [4 views đã kiểm]
                                      ↓ ref('bronze_*')
                                silver.stg_*/int_*    [chưa triển khai]
                                      ↓ ref(...)
                                gold.fct_*/mart_*     [chưa triển khai]
                                      ↓ tests + reconciliation + publish
                                Gold release → SQL / Streamlit [chưa triển khai]
```

| Đầu ra | Trạng thái kiểm chứng |
| --- | --- |
| Bootstrap CSV → PostgreSQL + ledger; retry | Đã chạy, tổng 100.889 dòng; retry skipped, không reset nguồn |
| PostgreSQL → DuckDB raw | Đã chạy full snapshot; hash/count/null/totals/lineage và read-only reopen đạt |
| 4 Bronze views + extraction_lineage macro | Đã build và đối soát raw ↔ Bronze; không mất/thừa/thay dữ liệu |
| dbt source/model data tests | **Chưa có trong project; 0 dbt test nodes chạy ở review thật** |
| Macros clean/string/safe arithmetic, Silver/Gold | Chưa triển khai; mẫu bên dưới là hướng dẫn |
| Guarded model-build action/refresh runner, Gold publish | Chưa triển khai; helper review một lần không thay runner |
| Streamlit, DAG Airflow, CDC | Chưa triển khai; nằm sau các mốc modeling/analytics đầu |

Trong toàn plan dùng đúng tên models thực **bronze_customer, bronze_product, bronze_region, bronze_ecom_sales**. Không còn dùng tên ví dụ brz_* hoặc brronze_ecom_sales. Các đoạn ghi “mẫu” cần bạn tạo và kiểm chứng, không phải file đã tồn tại.

<a id="requirements"></a>
## 2. Các yêu cầu chủ đạo

1. **Business dẫn đường:** gắn model/analysis với B01–B06; chốt grain, unit/currency, sales/profit semantics, order scope và null policy trước metric liên quan. Không suy net profit/gross sales hoặc causal discount từ tên cột.
2. **Ownership:** Python chỉ ghi raw; dbt đọc source raw và tạo Bronze/Silver/Gold. Bronze là explicit pass-through views; Silver clean/joins; Gold facts/marts có grain rõ.
3. **Không làm mất dữ liệu âm thầm:** không DISTINCT/dedup tùy ý, inner join drop orphan, trim/lower mã định danh một phía hoặc thay null tiền bằng 0. Conflict cần fail/quarantine có audit.
4. **Giữ kiểu và lineage:** tiền DECIMAL, không FLOAT; giữ _extraction_id/_extracted_at/_source_table. Không thay timestamp extraction bằng current_timestamp lúc dbt build.
5. **Tests có ý nghĩa:** unique + not_null trên đúng key; null/range/accepted_values theo contract, đối soát keys/nulls/totals trước/sau join và roll-up. Không test mọi cột not_null hoặc profit >= 0.
6. **Fail/warn rõ ràng:** sai PK/schema/precision, fan-out hoặc lệch totals block bước tiếp theo. Orphan đã biết giữ/report; warning/threshold chỉ khi có policy được review. Chưa chốt semantics thì block metric bị ảnh hưởng hoặc ghi provisional và scope rõ.
7. **Runtime đúng platform:** reuse services và ecom/refresh; manual scheduler OFF, kiểm live budget; một writer lock xuyên extract → dbt → reconcile → publish; đóng loader connection trước dbt. Không sửa registry/service/WSL để né limit.
8. **Serving an toàn:** Streamlit chỉ đọc immutable Gold release đã kiểm, không mở build candidate. Gold-only chưa tự bảo đảm privacy: review columns/grain; không đưa email/tên/customer rows private vào public report.
9. **Full snapshot trước:** mỗi extract tạo candidate mới, Gold ban đầu rebuild từ toàn snapshot. Chưa cần watermark/lookback/incremental. Airflow chạy theo lịch vẫn có thể là full snapshot batch.

### Tree triển khai

```text
ingestion/loaders/postgres_to_duckdb.py     # ĐÃ CÓ: raw loader
scripts/Invoke-Dev.ps1 + environment.py     # ĐÃ CÓ: environment/bootstrap/extract;
                                          # model-build action chưa có
dbt/
├── models/
│   ├── raw/sources.yml                    # ĐÃ CÓ; cần bổ sung column tests
│   ├── bronze/bronze_{customer,product,region,ecom_sales}.sql  # ĐÃ CÓ
│   ├── bronze/schema.yml                  # CẦN VIẾT
│   ├── silver/stg_{customers,products,regions,ecom_sales}.sql # CẦN VIẾT
│   ├── silver/int_order_lines_enriched.sql # CẦN VIẾT
│   ├── silver/int_orders_aggregated.sql    # SAU ORDER CONTRACT
│   ├── silver/schema.yml                  # CẦN VIẾT
│   ├── gold/fct_order_lines.sql, fct_orders.sql              # CẦN VIẾT
│   ├── gold/mart_product_performance.sql, mart_monthly_performance.sql
│   └── gold/schema.yml                    # CẦN VIẾT
├── macros/generate_schema_name.sql        # ĐÃ CÓ; model schemas bronze/silver/gold
├── macros/extraction_lineage.sql          # ĐÃ CÓ
├── macros/normalize_label.sql, safe_ratio.sql               # MẪU
├── tests/generic/same_rows_as.sql, unique_combination.sql   # MẪU
├── tests/bronze_sales_totals.sql, order_header_consistency.sql # MẪU
└── analyses/                              # B01–B06/Q01–Q15 khi có contracts
analysis/reports/                          # Evidence và insight đã rà PII
```

Không cần tạo tất cả files/marts cùng lúc. Source DDL được sinh từ typed contract, không duy trì DDL song song. Xem [Docker runbook](../docker.md) cho operations; [architecture](../architecture.md) cho topology.

<a id="raw"></a>
## 3. Raw · bootstrap và snapshot contract

| Nguồn | Raw / Bronze tương ứng | Key | Baseline rows |
| --- | --- | --- | ---: |
| customer.csv | raw.customer / bronze.bronze_customer | customer_id | 17.415 |
| product.csv | raw.product / bronze.bronze_product | product_code | 28.356 |
| region.csv | raw.region / bronze.bronze_region | region_code | 3.828 |
| ecom_sales.csv | raw.ecom_sales / bronze.bronze_ecom_sales | row_id | 51.290 |

100.889 dòng (~8,76 MiB CSV) là baseline đã kiểm, **không hardcode làm row-count target cho mọi snapshot**. Sales line không phải order. Baseline có 124 customer.gender null, sales orphan customer=0/product=2/region=2; các tập orphan có thể chồng nhau.

- CSV headers/keys được kiểm trong [csv_contracts.py](../../ingestion/sources/csv_contracts.py); types, required fields, schema signature và stats trong [table_contracts.py](../../ingestion/sources/table_contracts.py).
- Dates ISO YYYY-MM-DD; quantity BIGINT; income/sales/profit NUMERIC(20,2), discount NUMERIC(9,6), tọa độ NUMERIC(12,6). DuckDB giữ DECIMAL tương ứng. Khóa text giữ nguyên; chuỗi rỗng/NULL chỉ thành null khi contract cho phép.
- [Bootstrap](../../scripts/bootstrap/load_csv.py): owner non-admin, validate payload/hash/Decimal/date, PG transaction + advisory lock bao quanh tạo bốn bảng/COPY/reconcile/ledger. Lỗi rollback cả bốn; cùng baseline skip, input/schema khác fail; không DROP/TRUNCATE hoặc reset OLTP changes.
- [Extractor](../../ingestion/loaders/postgres_to_duckdb.py): reader non-admin, một REPEATABLE READ READ ONLY transaction cho bốn bảng, named cursors fetchmany(1000). Giữ Decimal/date, đối chiếu toàn business-value hash theo PK, rows/nulls/totals và lineage; commit/đóng writer rồi mở read-only. Lỗi chỉ cleanup candidate của lần thử và ghi failed receipt.

```python
# Trích ý chính ingestion/loaders/postgres_to_duckdb.py; đã có implementation.
with pg.transaction():
    pg.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
    guard_pg_identity(pg, 'ecom_reader')
    # Bốn bảng + thống kê trong cùng transaction; fetchmany(1000) -> raw writer.
```

fetchmany(1000) là chunk đọc, không phải watermark. Raw là typed source snapshot, không phải bản byte-for-byte của CSV. Receipt `validated_raw` / `storage_schema: raw` mới dùng được với raw source YAML. Candidate `validated_bronze` cũ và DataGrip inspection copy không tự migrate.

### Full snapshot, batch và incremental

Luồng hiện tại là **batch full snapshot**, dù chạy manual hay Airflow. Mỗi lần đọc đủ PostgreSQL hiện tại vào file mới; Bronze/Silver views đọc file đó, Gold dự kiến rebuild. Vì không chỉ chọn phần thay đổi nên chưa cần watermark/lookback. Full extraction lần sau phản ánh source updates/deletes hiện tại; không tự tạo lịch sử thay đổi/SCD.

Chỉ thiết kế incremental khi có nhu cầu và nguồn change tracking đáng tin: updated_at/tie-breaker hoặc CDC offset, delete handling, overlap/dedup, transactional checkpoint và replay. Lookback có giới hạn, không bắt được mọi update quá cũ. order_date và extraction_id không phải cursor đáng tin để bắt sửa đơn cũ. PG snapshot token phục vụ audit, không phải backup mở lại sau transaction; CSV chỉ tái lập baseline, lịch sử sau OLTP changes cần PG backup/change journal.

<a id="bronze"></a>
## 4. Bronze · phần đã viết và việc cần hoàn thiện

`dbt_project.yml` đang đặt folder bronze: schema bronze, materialized view; silver view; gold table. `generate_schema_name` giữ ba tên đó, cho phép dbt_test__audit chỉ với test nodes, chặn model ghi raw. Không đặt unique_key config thay cho unique test.

**Tham chiếu file đã có:** `dbt/models/bronze/bronze_ecom_sales.sql`:

```sql
-- Một row_id, giữ nguyên values và extraction lineage.
select
    row_id, order_id, order_date, customer_id, segment, region_code,
    product_code, quantity, sales, discount, profit,
    {{ extraction_lineage() }}
from {{ source('raw', 'ecom_sales') }}
```

Ba models còn lại giữ explicit source columns và lineage, cùng grain/key ở mục 3. Không JOIN/WHERE/DISTINCT trong pass-through Bronze. Product đã giữ product/category/subcategory gốc; chuẩn hóa nhãn làm tại Silver.

**Việc làm ngay:** raw sources.yml và bronze/schema.yml: descriptions, unique/not_null cho 4 keys, lineage checks, same_rows_as raw ↔ Bronze cho toàn cột; thêm singular totals test. Bốn views build thành công không đồng nghĩa các dbt tests này đã tồn tại/pass.

<a id="macros"></a>
## 5. Clean, chuẩn hóa và macros

### Quy tắc dữ liệu theo nhóm cột

| Nhóm | Xử lý dự kiến | Cách kiểm và giới hạn |
| --- | --- | --- |
| IDs | Giữ source text; map chỉ khi có policy áp dụng cả hai phía FK | Key sets/uniqueness; không lower/trim/dedup tự ý |
| Product/category/segment/geography labels | Trim; blank → null; đổi tên cột có docs | Test normalized value, null coverage; không gộp mã chỉ vì nhãn giống nhau |
| Enums như gender/marital_status | Profile rồi dùng mapping reference được duyệt; giữ unmapped flag | accepted_values chỉ sau chốt domain; không tự đoán enum/điền giới tính thiếu |
| Date/numeric | Raw đã typed; cast thêm chỉ có lý do; không mất precision | Invalid/overflow phải fail hoặc flag/quarantine theo criticality; date/birth/order rules cần contract |
| Missing money / ratios | Giữ null khác zero; sum/ratio trên population đã định nghĩa | Missing-money count; denominator zero trả null; không lấy AVG margin làm tổng margin |
| Duplicate keys | Fail hoặc quarantine có audit, giữ conflicting evidence | Không lấy ROW_NUMBER tùy ý; raw PK không thay downstream tests |
| Orphans | LEFT JOIN + 3 unknown flags, giữ source key và sales | Count/value coverage theo receipt/extraction; không strict FK rồi drop dữ liệu |
| PII | Private build, reports/serving chỉ fields cần thiết | Không log rows/email/tên; Gold phải rà privacy trước publication |

**Macro đã có — `dbt/macros/extraction_lineage.sql`:**

```sql
{% macro extraction_lineage() -%}
    _extraction_id,
    _extracted_at,
    _source_table
{%- endmacro %}
```

**Mẫu cần viết — `dbt/macros/normalize_label.sql`:**

```sql
{% macro normalize_label(expression) -%}
    nullif(trim({{ expression }}), '')
{%- endmacro %}
```

Dùng cho nhãn với SQL expression do developer viết, ví dụ 'product'; không nhận SQL từ user/API và không dùng mặc định cho IDs. LOWER/UPPER, regex collapse spaces hay mapping country/category chỉ thêm sau profiling vì có thể đổi ý nghĩa.

**Mẫu cần viết — `dbt/macros/safe_ratio.sql`:**

```sql
{% macro safe_ratio(numerator, denominator) -%}
    ({{ numerator }}) / nullif(({{ denominator }}), 0)
{%- endmacro %}
```

Ví dụ `{{ safe_ratio('sum(profit)', 'sum(sales)') }}`; denominator zero/null cho metric null, không tự 0%. Chỉ gọi profit margin sau khi chốt units và missing-money scope. Macro giảm lặp SQL, không thay việc xác nhận metric.

### Safe cast/date khi thực sự có input text mới

**Mẫu fragment cho Silver sau này**, không áp lại hàng loạt lên raw hiện đã typed:

```sql
-- Ví dụ cột raw_date_text mới trong tương lai; hiện không tồn tại trong 4 nguồn.
select
    raw_date_text,
    try_cast(raw_date_text as date) as parsed_date,
    raw_date_text is not null
        and try_cast(raw_date_text as date) is null as is_invalid_date
from future_text_input
```

TRY_CAST trả null khi không cast được; phải đếm/flag lỗi và test. Nếu critical field không được phép sai, fail gate thay vì âm thầm nuốt null. Không coi cast thành công là đủ: numeric casts vẫn có thể làm tròn; loader hiện reject input vượt precision thay vì làm tròn tiền. Không tạo macro safe_cast chung chỉ để che contract violations.

<a id="silver"></a>
## 6. Silver · staging và enrichment

### Bốn staging models

| File cần viết | Grain | Nội dung |
| --- | --- | --- |
| dbt/models/silver/stg_ecom_sales.sql | row_id | Giữ keys/date/finance/lineage; chuẩn hóa segment label theo policy |
| dbt/models/silver/stg_products.sql | product_code | product → product_name; normalize labels; giữ product_code |
| dbt/models/silver/stg_customers.sql | customer_id | Chuẩn hóa thuộc tính được duyệt, giữ null và unmapped flags; PII private |
| dbt/models/silver/stg_regions.sql | region_code | Chuẩn hóa city/state/country/region/market labels; giữ coordinates/keys |

**Mẫu — `dbt/models/silver/stg_products.sql`:**

```sql
select
    product_code,
    {{ normalize_label('product') }} as product_name,
    {{ normalize_label('category') }} as category,
    {{ normalize_label('subcategory') }} as subcategory,
    {{ extraction_lineage() }}
from {{ ref('bronze_product') }}
```

**Mẫu — `dbt/models/silver/stg_ecom_sales.sql`:**

```sql
select
    row_id, order_id, order_date, customer_id,
    {{ normalize_label('segment') }} as segment,
    region_code, product_code, quantity, sales, discount, profit,
    {{ extraction_lineage() }}
from {{ ref('bronze_ecom_sales') }}
```

Customer/region làm tương tự, explicit columns; không cast lại tiền/date khi type đã đúng. Viết descriptions và column-level tests ở `dbt/models/silver/schema.yml`. Các nhãn thay đổi đúng rule nên **không** dùng exact-value test toàn cột giữa raw và Silver; dùng kiểm projection giữ nguyên cho keys/finance/lineage và test riêng giá trị normalized.

### Join bảo toàn sales

**Mẫu — `dbt/models/silver/int_order_lines_enriched.sql`**, sau khi đủ bốn stg và dimension keys unique:

```sql
select
    s.*,
    p.product_name, p.category, p.subcategory,
    r.country, r.market,
    c.customer_id is null as is_unknown_customer,
    p.product_code is null as is_unknown_product,
    r.region_code is null as is_unknown_region
from {{ ref('stg_ecom_sales') }} s
left join {{ ref('stg_products') }} p on s.product_code = p.product_code
left join {{ ref('stg_regions') }} r on s.region_code = r.region_code
left join {{ ref('stg_customers') }} c on s.customer_id = c.customer_id
```

Flag dựa trên lookup key, không phải nhãn: product_name null của product hợp lệ khác product_code không match. Giữ source product/region/customer codes kể cả khi orphan; unknown flag phải khớp receipt của snapshot, không hardcode 2. Không lấy tên/email customer vào enrichment nếu câu hỏi chưa cần.

### Order grain trước roll-up

`dbt/models/silver/int_orders_aggregated.sql` chỉ viết sau xác nhận scope order_id. Nếu global order_id được xác nhận thì order_key có thể chính là order_id; nếu không, dùng bộ business fields đã xác minh và kiểm không collision. Không tự ghép order_id+customer_id để che header conflict.

Trước roll-up kiểm mỗi order key có một customer/date/segment theo contract. Region chỉ ép single-value nếu được chọn làm thuộc tính cấp đơn; không suy từ grain dòng. Nếu conflict, fail hoặc quarantine với excluded coverage, không MIN/MAX chọn đại header.

Output dự kiến: order_key, validated headers, line_count, quantity, sales_total, profit_total, missing-money counts, is_financial_complete và extraction_id. Missing money phải được gắn cờ; không tính loss-order rate/AOV trên đơn chưa đủ điều kiện mà không công bố eligibility.

<a id="gold"></a>
## 7. Gold · facts/marts gắn business questions

Gold materialized table ban đầu rebuild toàn bộ trong private candidate; không incremental/merge theo timestamp trong MVP. Dimensions chỉ tạo khi cần dùng lại, không copy mọi cột PII từ Bronze.

| Model dự kiến | Grain / câu hỏi | Contract chính |
| --- | --- | --- |
| fct_order_lines | row_id; B01–B04 | Giữ đủ sales lines, keys/finance/unknowns; đối soát Silver |
| fct_orders | order_key; B01/B02/B04/B05 | Header và order scope đã qua gate; totals/eligible order count khớp line roll-up |
| dim_products, dim_regions, dim_customers, dim_date | Một dimension key/date khi cần | Keys unique, lookup policy, current-state semantics, PII review |
| mart_product_performance | month × product_code cho mẫu MVP; B03 | Contribution/totals; product identity; không gộp mã theo tên |
| mart_monthly_performance | month × market × segment; B04 | Calendar/period coverage, ratio of sums; unknown market/segment được giữ |
| mart_customer_rfm, order-history models | customer × as_of_date; B05/P2 | Fixed window/as-of, scoring/ties, không future leakage |
| order-product bridge, mart_market_basket | order × product; rồi ordered product pair × window; B06/P2 | Distinct products/order, không self-pair; đủ support và đúng denominator |

**Mẫu — `dbt/models/gold/fct_order_lines.sql`:**

```sql
select
    row_id, order_id, order_date,
    customer_id, product_code, region_code,
    segment, country, market, product_name, category, subcategory,
    quantity, sales, discount, profit,
    is_unknown_customer, is_unknown_product, is_unknown_region,
    {{ extraction_lineage() }}
from {{ ref('int_order_lines_enriched') }}
```

customer_id là identifier cần bảo vệ; fact này ở private build/internal analysis. Publication chỉ chọn models/columns đã review; dashboard public mặc định dùng aggregates, không phát tán raw/customer-level file.

**Mẫu — `dbt/models/gold/mart_monthly_performance.sql`:**

```sql
-- Grain month x market x segment. Hiện chỉ có line_count, không gọi là orders.
select
    date_trunc('month', order_date)::date as month,
    market, segment,
    count(*) as line_count,
    sum(quantity) as quantity,
    sum(sales) as sales,
    sum(profit) as profit,
    count(*) - count(sales) as missing_sales_lines,
    count(*) - count(profit) as missing_profit_lines,
    case when count(sales) = count(*) and count(profit) = count(*)
         then {{ safe_ratio('sum(profit)', 'sum(sales)') }}
    end as profit_margin
from {{ ref('fct_order_lines') }}
group by 1, 2, 3
```

SUM(sales/profit) vẫn là tổng giá trị đã quan sát; nếu missing-money counts > 0 thì không trình bày là tổng đầy đủ. Dashboard/analysis phải công bố coverage hoặc block KPI theo contract. Currency chưa rõ thì chưa so tài chính xuyên scope không tương thích.

Product mart tương tự nhưng group theo `month, product_code`, giữ counts/quantity/sales/profit và coverage. Không cộng order_count ở nhiều sản phẩm như tổng distinct orders toàn sàn. AOV/order loss làm từ fct_orders sau order gate, không lấy số sales lines làm số đơn.

Monthly YoY cần date spine và join đúng tháng năm trước; thiếu baseline trả null/flag, tránh LAG trên tập tháng khuyết. Dữ liệu thiếu tháng khác sales thực sự bằng 0, chưa tự COALESCE. RFM/basket chỉ mở rộng khi điều kiện B05/B06 trong [business plan](business-questions.md) đạt.

<a id="tests"></a>
## 8. Test matrix và mẫu triển khai

### Matrix tối thiểu cho từng model

| Nguồn/model | Key / unique grain | Tests riêng và đối soát cần có |
| --- | --- | --- |
| raw.customer / bronze_customer | customer_id unique + not_null | Toàn business values + 3 lineage columns raw ↔ Bronze exact; gender nullable; income precision |
| raw.product / bronze_product | product_code unique + not_null | Exact raw ↔ Bronze; nhãn được null theo contract, không unique product name |
| raw.region / bronze_region | region_code unique + not_null | Exact raw ↔ Bronze; types tọa độ; range chỉ sau rule hợp lệ được duyệt |
| raw.ecom_sales / bronze_ecom_sales | row_id unique + not_null | Required source columns, lineage, exact rows/nulls/quantity/sales/profit; không unique order_id, không profit>=0 |
| stg_customers | customer_id unique + not_null | Key set/count/lineage và values giữ nguyên ngoài fields clean; enum/unmapped/null coverage |
| stg_products | product_code unique + not_null | Key set/count giữ nguyên; product_name/category/subcategory đúng normalize_label; blank/null fixture |
| stg_regions | region_code unique + not_null | Key set/count, coordinates/lineage giữ nguyên; mapping geography có audit |
| stg_ecom_sales | row_id unique + not_null | Key/date/finance/lineage projection khớp Bronze; segment clean đúng rule; missing-money/discount profiling |
| int_order_lines_enriched | row_id unique + not_null | Sales projection khớp stg; no fan-out/missing rows; unknown flags khớp actual lookup và receipt |
| int_orders_aggregated | order_key unique + not_null | Header consistency, eligible/excluded populations; line→order count/totals/missing-money coverage |
| fct_order_lines | row_id unique + not_null | Khớp Silver projection; lookup-or-unknown-flag, financial completeness; không strict FK cho orphan hợp lệ |
| fct_orders | order_key unique + not_null | Khớp int_orders_aggregated; totals/order counts/eligibility; loss flag chỉ khi profit đủ dữ liệu |
| dim_products/regions/customers/date nếu tạo | dimension key/date unique + not_null | Business mapping/PII/date coverage; current-state không giả làm SCD lịch sử |
| mart_product_performance | month × product_code unique; month/code required | Qty/sales/profit và counts khớp facts cùng scope; rank/ties/share rules |
| mart_monthly_performance | month × market × segment unique; month required | Ratio of sums, null/unknown buckets; sums/counted lines khớp facts; full/partial period và YoY baseline |
| mart_customer_rfm (P2) | customer_id × as_of_date unique + required | Window/as-of, no future rows, scoring/ties; reconcile distinct orders/sales |
| order-product bridge / mart_market_basket (P2) | order×product / ordered pair×window unique | Distinct presence, no self-pair, support/confidence in [0,1], correct N and sample thresholds |

Shared tests: _extraction_id/_extracted_at/_source_table not_null và đúng receipt của candidate; keys không đổi ngoài mapping reviewed. Unknown dimension buckets được phép null ở nhãn/market theo policy và vẫn thuộc totals. accepted_values/ranges chỉ sau profiling/contract; không copy enum từ vài sample. Test severity default error cho integrity gates; warning không phải cách bỏ qua vấn đề chưa có policy.

### Source YAML: mở rộng file đã có

**Mẫu fragment — `dbt/models/raw/sources.yml`**, merge vào product table entry của source raw, không khai báo source thứ hai cùng tên:

```yaml
- name: product
  columns:
    - name: product_code
      data_tests: [unique, not_null]
    - name: _extraction_id
      data_tests: [not_null]
    - name: _extracted_at
      data_tests: [not_null]
    - name: _source_table
      data_tests: [not_null]
```

Mở rộng cùng pattern cho customer/customer_id, region/region_code và ecom_sales/row_id, thêm required source fields theo typed contract. Source PK đã enforce không có nghĩa downstream view luôn giữ đúng key.

### Generic test exact projection

**Mẫu — `dbt/tests/generic/same_rows_as.sql`:** 0 dòng sai khác là pass; EXCEPT ALL hai chiều bắt cả duplicate, null và changed values. Chỉ dùng cho projection có cùng column names/types:

```sql
{% test same_rows_as(model, compare_model, column_names) %}
    {% set fields = [] %}
    {% for name in column_names %}
        {% do fields.append(adapter.quote(name)) %}
    {% endfor %}
    with missing_or_changed as (
        select {{ fields | join(', ') }} from {{ compare_model }}
        except all
        select {{ fields | join(', ') }} from {{ model }}
    ), extra_or_changed as (
        select {{ fields | join(', ') }} from {{ model }}
        except all
        select {{ fields | join(', ') }} from {{ compare_model }}
    )
    select * from missing_or_changed
    union all
    select * from extra_or_changed
{% endtest %}
```

**Mẫu — `dbt/models/bronze/schema.yml`:** cả 4 model keys và ví dụ exact test đầy đủ cho sales. Bổ sung not_null cho ba lineage columns trên mọi model; thêm same_rows_as cho customer/product/region với toàn source columns + lineage theo table_contracts/csv_contracts.

```yaml
version: 2
models:
  - name: bronze_customer
    description: One customer_id; private source projection.
    columns:
      - name: customer_id
        data_tests: [unique, not_null]
  - name: bronze_product
    description: One product_code; business SKU identity remains open.
    columns:
      - name: product_code
        data_tests: [unique, not_null]
  - name: bronze_region
    description: One region_code.
    columns:
      - name: region_code
        data_tests: [unique, not_null]
  - name: bronze_ecom_sales
    description: One source row_id, not one order.
    columns:
      - name: row_id
        data_tests: [unique, not_null]
      - name: order_id
        data_tests: [not_null]
      - name: _extraction_id
        data_tests: [not_null]
      - name: _extracted_at
        data_tests: [not_null]
      - name: _source_table
        data_tests: [not_null]
    data_tests:
      - same_rows_as:
          arguments:
            compare_model: source('raw', 'ecom_sales')
            column_names: [row_id, order_id, order_date, customer_id, segment,
                           region_code, product_code, quantity, sales, discount,
                           profit, _extraction_id, _extracted_at, _source_table]
          config:
            store_failures: false
```

`arguments:` theo dbt Core 1.12.6 đang ghim. ref/source arguments được dbt render thành relations; không dùng user-supplied SQL. Giữ failed rows private, không bật store_failures/public reports tùy ý vì có PII.

### Singular totals test

**Mẫu — `dbt/tests/bronze_sales_totals.sql`:** dễ debug nhưng không thay exact-value test; hai dòng đổi giá trị bù nhau có thể giữ nguyên totals:

```sql
with raw_totals as (
    select count(*) as rows_n, sum(quantity) as quantity_sum,
           sum(sales) as sales_sum, sum(profit) as profit_sum,
           count(sales) as sales_nonnull, count(profit) as profit_nonnull
    from {{ source('raw', 'ecom_sales') }}
), bronze_totals as (
    select count(*) as rows_n, sum(quantity) as quantity_sum,
           sum(sales) as sales_sum, sum(profit) as profit_sum,
           count(sales) as sales_nonnull, count(profit) as profit_nonnull
    from {{ ref('bronze_ecom_sales') }}
)
select 'raw_bronze_totals_mismatch' as issue
from raw_totals r cross join bronze_totals b
where r.rows_n is distinct from b.rows_n
   or r.quantity_sum is distinct from b.quantity_sum
   or r.sales_sum is distinct from b.sales_sum
   or r.profit_sum is distinct from b.profit_sum
   or r.sales_nonnull is distinct from b.sales_nonnull
   or r.profit_nonnull is distinct from b.profit_nonnull
```

IS DISTINCT FROM xử lý null an toàn; không COALESCE tổng null thành zero. Enrichment có thể dùng same_rows_as với compare_model `ref('stg_ecom_sales')` và toàn cột stg sales không đổi; không đưa columns mới vào projection so sánh.

### Unique cho composite grain

**Mẫu — `dbt/tests/generic/unique_combination.sql`:**

```sql
{% test unique_combination(model, column_names) %}
    {% set fields = [] %}
    {% for name in column_names %}
        {% do fields.append(adapter.quote(name)) %}
    {% endfor %}
    select {{ fields | join(', ') }}, count(*) as records_n
    from {{ model }}
    group by {{ fields | join(', ') }}
    having count(*) > 1
{% endtest %}
```

**Mẫu — `dbt/models/gold/schema.yml`:**

```yaml
version: 2
models:
  - name: mart_monthly_performance
    description: One month x market x segment, including unknown buckets.
    columns:
      - name: month
        data_tests: [not_null]
    data_tests:
      - unique_combination:
          arguments:
            column_names: [month, market, segment]
```

Composite uniqueness không thay not_null: bổ sung required components theo grain contract; market/segment unknown được giữ theo policy ở mẫu này. Không hash/concat thiếu delimiter để làm fake unique key.

### Order header gate trước fct_orders

**Mẫu — `dbt/tests/order_header_consistency.sql`**, chỉ sau khi order_id được xác nhận global order key và customer/date/segment được chọn làm required order headers. Nếu scope khác, đổi GROUP BY theo order_key đã được review:

```sql
select order_id
from {{ ref('int_order_lines_enriched') }}
group by order_id
having count(distinct customer_id) <> 1
    or count(distinct order_date) <> 1
    or count(distinct segment) <> 1
    or count(customer_id) <> count(*)
    or count(order_date) <> count(*)
    or count(segment) <> count(*)
```

Không tự áp giả định một segment/đơn khi business chưa chốt; nếu null segment được phép phải có unknown-header policy và test phù hợp. Gate sai thì không roll-up rồi trình bày order metrics như đúng.

### Fixtures kiểm thử logic, không chỉ test pass trên baseline sạch

| Ca tự sinh | Kỳ vọng |
| --- | --- |
| Mất/trùng một source row; đổi profit bù giữa hai dòng; null → zero; sai lineage | same_rows_as fail; không để totals-only che lỗi |
| Blank/space/null label, label có accent; identifier có space/case khác | Normalize theo rule nhãn; IDs không bị tự sửa |
| Date sai, numeric overflow/rounding, denominator 0 | Fail/flag đúng criticality; không nuốt lỗi hoặc tạo infinity/0% giả |
| Duplicate dimension key, missing product/region | Duplicate fail; missing lookup giữ sales và đúng unknown flag |
| Order nhiều dòng cùng sản phẩm, header conflict | Không nhầm lines thành orders; conflict bị chặn trước roll-up |
| Thiếu tháng baseline/partial month | YoY null/coverage flag; không LAG sai kỳ hoặc tự fill 0 |
| RFM giao dịch sau as-of; basket product lặp/single-product order | Không future leakage; presence distinct; denominator đúng |

Unit tests dbt cho logic model hoặc fixture integration riêng được thêm khi model tương ứng triển khai. Không chỉnh raw thật để tạo ca lỗi. Mẫu mới trong plan chưa được chạy như test suite production.

<a id="run"></a>
## 9. Cách chạy, runtime và checkpoint

### Những lệnh đã có

Theo [Docker runbook](../docker.md), dùng đúng secrets/DB/roles đã provision; không tạo lại môi trường để refresh. Đọc platform AGENTS/ARCHITECTURE/ONBOARDING/resources.json trước Docker/PG/policy changes, không in platform .env. Các đường dẫn sau là máy maintainer, máy clone tự cấu hình:

```powershell
Set-Location 'D:/Dev/Project/e_commerce'
$ecomPlatformDir = 'D:/Dev/Project/airflow-platform'
.\scripts\Invoke-Dev.ps1 -Action Build -PlatformDir $ecomPlatformDir
.\scripts\Invoke-Dev.ps1 -Action Check -Role reader -PlatformDir $ecomPlatformDir
# Chỉ khi khởi tạo nguồn lần đầu hoặc kiểm identical retry; không reset nguồn:
.\scripts\Invoke-Dev.ps1 -Action Bootstrap -Role owner -PlatformDir $ecomPlatformDir
# Tạo raw candidate mới mỗi lần; không tự chạy dbt tiếp:
.\scripts\Invoke-Dev.ps1 -Action Extract -Role reader -PlatformDir $ecomPlatformDir
```

Owner `ecom_owner`, reader `ecom_reader`, DB `ecom_source_dev`; container DNS warehouse-laplaptech:5432 trên laplaptech-lab; host port đọc cấu hình platform. Không dùng admin LapLapTech hoặc Airflow metadata DB. Secrets `.local/secrets/owner.password`, `reader.password` là file đang dùng; không tự regenerate/reset nếu DB đã tồn tại.

Môi trường thêm **0 persistent services**. Runtime ecom/refresh 1024 MiB/1 CPU, dbt_threads=1, hai platform_memory slots; DuckDB 512 MB/1 thread, spill max 1 GB. Manual CLI không được Airflow pool admission; scheduler OFF và live budget phải đạt. Không tắt project khác/đổi resource policy/WSL âm thầm. Khi có DAG dùng BudgetDockerOperator; không override pool/pool_slots/mem_limit/cpus hoặc dựng pool riêng.

Fixture ingestion đã có, không sửa nguồn thật:

```powershell
python .\tests\integration\test_ingestion.py --platform-dir $ecomPlatformDir
```

Host Python chỉ dùng stdlib để tạo PostgreSQL fixture/network riêng + runtime, synthetic data; không mount CSV/secrets/volumes thật. Cần scheduler OFF và budget fixture PG 384 MiB + runtime 1024 MiB, cleanup scope fixture. Không cần cài DuckDB/psycopg trên host để dùng lệnh này.

### Build/test runner cần triển khai trước khi tự chạy dbt

`scripts/Invoke-Dev.ps1` hiện **chưa có Action build/test models**, `scripts/environment.py` mới có environment/bootstrap/extract. One-off Bronze review đã giữ lock và admission riêng, chưa phải entrypoint hỗ trợ chung. Yêu cầu action/runner mới:

1. Chọn candidate bằng validated_raw receipt/extraction_id rõ ràng, không tự mở latest tùy ý hoặc `.local/datagrip`. Validate path dưới ecom build/candidates, schema/layout, source contract, raw business hashes/counts/nulls/totals và lineage đúng receipt.
2. Giữ runtime file lock trên shared project build volume; trong refresh đầy đủ, lock giữ suốt extract → dbt → reconcile → publish. Manual writers dùng cùng protocol; DAG concurrency 1 không thay file lock.
3. Đóng connection loader trước subprocess dbt. Profile trỏ ECOM_DUCKDB_PATH đúng candidate, DBT_THREADS=1; logs/target/artifacts theo run trong ecom-dev-artifacts. Không ghi /app root read-only hoặc file inspection/serving release.
4. Test sources → build models/tests → independent reconciliation → close writers/read-only reopen. Ghi run_results/manifest, code hash/revision, extraction_id, parameters và failure state; retry không append double-count full snapshots.
5. Lỗi quality gate thì dừng, không publish hoặc đổi active release pointer. Build được không đồng nghĩa metric semantics đúng.

**Lệnh mục tiêu bên trong guarded runtime sau khi action có**, không chạy ngoài lock/budget để bypass scaffold:

```text
dbt test --project-dir /app/dbt --profiles-dir /app/config --select source:raw
dbt build --project-dir /app/dbt --profiles-dir /app/config --select path:models/bronze
dbt test --project-dir /app/dbt --profiles-dir /app/config --select bronze_sales_totals
dbt build --project-dir /app/dbt --profiles-dir /app/config --select +stg_ecom_sales +stg_products
dbt build --project-dir /app/dbt --profiles-dir /app/config --select path:models/silver path:models/gold
```

Không nhầm `dbt build` với thực thi files trong dbt/analyses: analyses cần bước chạy query riêng và capture evidence. Không dùng dbt debug/parse/compile để tuyên bố data tests hoặc business findings đã đạt.

### Checkpoint triển khai

| Mốc | Bài thực hành / đầu ra | Điều kiện đi tiếp |
| --- | --- | --- |
| C0 · Đã có | Source/raw + 4 Bronze views | Evidence mục 10; giữ đúng names/snapshot, không ghi đè lịch sử |
| C1 · Việc ngay | Raw source tests, Bronze schema.yml, generic/singular tests + guarded build/test action | Bốn keys/lineage/projections/totals đạt, fixture lỗi fail đúng; lưu artifacts |
| C2 | normalize_label + stg_products/stg_ecom_sales, rồi customers/regions | Keys/types/finance/lineage giữ nguyên; clean labels đúng rule; null/unmapped coverage rõ |
| C3 | int_order_lines_enriched, unknowns và order contract | No fan-out/drop; reconcile counts/totals; order scope/header/missing-money policy được chốt |
| C4 | fct_order_lines/fct_orders, marts monthly/product vừa đủ | Grain/roll-up/period/currency gates đạt; facts hỗ trợ B01–B04 |
| C5 | SQL analyses và báo cáo evidence | Metric definitions + units/window/population; 3–5 findings nếu đủ evidence, actions/caveats/validation |
| C6 | Gold-only publish → Streamlit | Chỉ chọn approved Gold models/columns, PII review, immutable release/read-only reopen, atomically switch active pointer; publish failure giữ release tốt cũ |
| C7 · Sau P1 | RFM/basket, Airflow DAG, CDC hoặc standalone portability | Review nhu cầu, contracts và resources riêng; không dựng thêm infra chỉ để tăng số tools |

Gold serving chạy tách writer; request dùng một immutable release. Bản inspection DataGrip không phải serving release và không tự refresh sau build. Chưa có retention tự động: logs/candidates/artifacts/releases vẫn tăng; chỉ cleanup đúng scope khi không có writer, không prune --volumes. Standalone Compose cho người chưa có shared platform chưa triển khai.

<a id="evidence"></a>
## 10. Evidence đã có · giữ từ 4 plan cũ

### Bootstrap và raw extraction · 24/10/2026

- Bootstrap nạp 100.889 dòng vào bốn source tables và baseline ledger; identical retry trả skipped, không reset nguồn hoặc OLTP changes.
- Source contract version `ecom-source-v1`; source schema/CSV contract không đổi khi đổi output Bronze cũ sang raw.
- Raw extraction_id: **28f756d06b334dfca12f078774f00db9**; status `validated_raw`, storage_schema `raw`.
- Snapshot timestamp: `2026-10-24T12:10:41.882644+00:00`.
- Counts customer/product/region/sales: **17.415 / 28.356 / 3.828 / 51.290**. Hash toàn business values, rows/nulls/totals, lineage và read-only reopen đạt.
- Orphans customer=0/product=2/region=2; preserve_and_report, không strict FK làm drop rows; có thể chồng nhau.

### Bronze review · 24/10/2026

- Sửa customer sai macro `extraction_leneage`/thiếu (), region `sourec()`, sales `segement`; file brronze_ecom_sales.sql đổi thành bronze_ecom_sales.sql. Product và extraction_lineage đúng.
- Candidate trước review chưa có Bronze; sau sửa/build có đúng **4 VIEW** ở schema bronze, tên/models/counts/key như mục 3. Không tạo thêm full physical copy.
- Source dependencies, column names/types/DECIMAL, key uniqueness/not-null đạt. EXCEPT ALL hai chiều toàn cột business + lineage = 0; business hash/counts/nulls/totals khớp raw/receipt. Raw trước/sau dbt không đổi; orphans vẫn 0/2/2.
- Run: **bronze-review-4b33cfd463b7410b898f0aead34d370b**, hoàn tất `2026-10-24T12:49:29.805491+00:00`.
- dbt Core 1.12.6 / dbt-duckdb 1.11.0 / DuckDB 2.0.0; model results = 4 success; **dbt data tests executed = 0**. Independent reconciliation sau build đạt, không gọi đó là test suite dbt đã triển khai.
- Code hash tại lần build: `676be2b36412ac02ec7104f709a09701ff273da589caa1fe8464d5b29cdf9e2f`.
- Cgroup: memory.max=1073741824, cpu.max=100000/100000, pids.max=256; budget/manual window và writer lock qua validate/dbt/reconciliation đạt. Không sửa PostgreSQL hoặc Gold serving releases.

### Fixtures và mẫu học đã kiểm

12 synthetic integration checks đạt ngày 24/10: schema guard/internal test audit; writer lock/release; COPY atomic rollback; bootstrap/retry; changed input giữ nguồn; Decimal precision; reader permissions; partial candidate cleanup; consistent snapshot/new candidate; raw đủ 4 bảng và không tạo dbt layers; retry giữ OLTP changes; database/role guards.

Các mẫu plan cũ được tách vào **project tạm/synthetic data**: lineage + normalize_label macros, Bronze product/sales, Silver products, YAML, same_rows_as và singular totals; có 15 model/test results success/pass. same_rows_as bắt 5 ca: mất dòng, duplicate, changed values bù tổng, null→zero, đổi lineage. Đây không phải tests trên candidate thật hoặc bảo đảm mọi mẫu mới bên trên đã chạy. Composite test, safe_ratio, Gold/order examples và matrix mới vẫn cần implement/test tương ứng.

### Paths để trace evidence

| Artifact | Path / volume |
| --- | --- |
| Candidate raw + Bronze đã review | `/state/build/candidates/28f756d06b334dfca12f078774f00db9/ecom_analytics.duckdb` · ecom-dev-build |
| Raw receipt | `/state/artifacts/extract/28f756d06b334dfca12f078774f00db9/receipt.json` · ecom-dev-artifacts |
| Bronze review receipt/logs/target | `/state/artifacts/bronze-review/bronze-review-4b33cfd463b7410b898f0aead34d370b/` · ecom-dev-artifacts |
| Bootstrap receipts | `/state/artifacts/bootstrap/<run_id>/receipt.json` · ecom-dev-artifacts |
| Future Gold releases | `/state/releases/` · ecom-dev-releases; chưa publish |
| Private legacy inspection | `.local/datagrip/ecom_analytics.duckdb` + receipt; layout Bronze cũ, chưa có 4 views mới, không tự refresh |

Đường dẫn /state là Linux trong Docker volumes, không phải file ổ D:. Secrets `.local/secrets` giữ nguyên; không xóa như cache. Candidates/inspection chứa dữ liệu khách hàng, không commit, bake image hoặc share nguyên file. DB/roles/registry trên máy này đã provision; máy khác tự onboard theo platform của họ, không tự rename/migrate database cũ.

## 11. Nguồn và phạm vi cập nhật

[Business questions](business-questions.md) giữ metric/decision contracts; [data modeling](../data-modeling.md) là reference grain; [Docker](../docker.md) là runbook, [architecture](../architecture.md) là topology; [CDC](../cdc-plan.md) là chặng tùy chọn. Hai file trong docs/plans là đầu mối plan, không giữ bản plan rời theo ngày.

Tham khảo chính thức: [dbt sources](https://docs.getdbt.com/docs/build/sources), [data tests](https://docs.getdbt.com/docs/build/data-tests), [custom generic tests](https://docs.getdbt.com/best-practices/writing-custom-generic-tests), [incremental models](https://docs.getdbt.com/docs/build/incremental-models), [DuckDB casting](https://duckdb.org/docs/current/sql/expressions/cast).

Ngày 25/10 chỉ hợp nhất và làm rõ tài liệu từ code/records đã có; không đọc lại warehouse để tuyên bố freshness, không chạy thêm models/tests, không deploy Docker/DAG/Gold hoặc sinh business insights trong lần cập nhật này.
