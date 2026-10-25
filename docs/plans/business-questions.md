# Business questions · trọng tâm commercial analytics

> Cập nhật 25/10/2026. Đây là một trong **hai plan chính thức**: file này trả lời “phân tích để hỗ trợ quyết định gì?”, [raw-to-gold.md](raw-to-gold.md) trả lời “xây, clean và kiểm chứng dữ liệu thế nào?”. Các kết quả kiểm kỹ thuật là evidence ngày 24/10, không phải insight kinh doanh.

**Hiện trạng:** 4 CSV đã bootstrap vào PostgreSQL, extract vào DuckDB raw và 4 Bronze views đã build/đối soát. dbt data tests, Silver/Gold, analyses, Gold publication và Streamlit chưa triển khai. Không lấy row counts/loader receipts làm phát hiện thương mại.

**Cách dùng khi làm:** chọn một B-ID → ghi metric/grain/population/kỳ và điều kiện còn mở → chọn model/tests cần thiết trong raw-to-gold → viết SQL → review evidence và kết luận. P1 làm B01–B04; P2 B05–B06 sau khi đủ điều kiện.

## 1. Mục tiêu

Tạo một luồng phân tích có thể giải thích và chạy lại:

```text
Vấn đề / quyết định kinh doanh
    → câu hỏi phân tích
    → metric contract và grain
    → raw / Bronze contract → dbt Silver / Gold + tests
    → SQL và bằng chứng
    → insight, hành động đề xuất, cách kiểm chứng
```

Mỗi model phải phục vụ câu hỏi hoặc kiểm soát chất lượng cụ thể. Không cần một mart cho mỗi câu hỏi. Giữ kiến trúc Docker hiện tại trong chặng này; Airflow/CDC/dashboard là backlog sau các kết quả phân tích đầu tiên, trừ việc kỹ thuật cần thiết để chạy dbt đúng candidate/resource/lock.

Vai trò Commercial/Finance/CRM dưới đây là **stakeholders giả định của bài tập**, chưa phải người đã được phỏng vấn hoặc yêu cầu doanh nghiệp đã xác nhận.

## 2. Những câu hỏi business cần làm rõ trước

| Câu hỏi cần chốt | Tại sao ảnh hưởng kết luận? | Nơi xác minh |
| --- | --- | --- |
| Ưu tiên tăng sales, tăng profit hay giảm đơn lỗ? | Quyết định cách xếp hạng và trade-off | Người dùng/giả định bài tập; đề xuất ưu tiên profit cùng sales/margin |
| sales trước hay sau discount; profit đã trừ những chi phí nào? | Tránh trừ discount hai lần hoặc gọi profit là net profit | Tài liệu nguồn/source owner; không thể suy ra chắc chắn chỉ từ số |
| Đơn vị tiền tệ là gì, đã chuẩn hóa giữa thị trường chưa? | Chưa rõ thì tổng tiền/ranking xuyên thị trường chưa đủ ý nghĩa tài chính | Metadata nguồn, không suy diễn currency từ country |
| Một order_id nhận diện đơn trong scope nào? | AOV, đơn lỗ, RFM và basket đều phụ thuộc order grain | Profiling và business definition; kiểm customer/date/segment/header |
| product_code có phải SKU nghiệp vụ không? | Ranking và basket theo mã có thể khác ranking theo sản phẩm thật | Profiling code/name/category và xác nhận nguồn |
| Kỳ dữ liệu có đủ/tháng nào còn dở, comparison period là gì? | Tránh so tháng chưa đủ với tháng đủ hoặc YoY thiếu baseline | Date coverage và snapshot metadata |
| Orphan/null xử lý và công bố thế nào? | Không bỏ doanh thu hoặc che nhóm chưa phân loại | Policy preserve_and_report; LEFT JOIN, unknown flags và coverage |
| VIP, inactivity và minimum basket support chọn theo căn cứ nào? | Không biến ngưỡng tùy ý thành kết luận churn/cross-sell | Distribution/cadence mua và giả định được ghi rõ |

Chưa có câu trả lời thì ghi open/provisional và phạm vi kết luận bị hạn chế. Không điền currency, churn window, support threshold hoặc KPI target giả cho đủ tài liệu.

## 3. Backlog câu hỏi theo quyết định

Các B-ID tổ chức bài toán; Q01–Q15 trong context là bộ query hỗ trợ, không phải 15 insight đã có.

| Ưu tiên | Vấn đề / câu hỏi | Quyết định được hỗ trợ | Metrics / cuts | dbt đầu ra dự kiến | Query liên quan |
| --- | --- | --- | --- | --- | --- |
| P1 · B01 | Sales và profit phân bổ ra sao? Nhóm nào sales lớn nhưng margin thấp, phần lỗ tập trung ở đâu? | Commercial/Finance chọn nhóm cần điều tra trước | Sales, profit, margin, loss-order rate; market/segment/category | fct_order_lines, fct_orders; analyses trên facts | Q1, Q2, Q6, Q7, Q10 |
| P1 · B02 | Discount cao có đi cùng margin thấp/đơn lỗ cao không, trong các nhóm sản phẩm và kỳ tương đương? | Rà pricing/promotion, chọn giả thuyết cần thử | AVG discount theo dòng, phân bố discount, profit/margin, loss rate; category/segment/time | Facts + analysis discount; chỉ tạo mart nếu cần dùng lại | Q5, Q7 |
| P1 · B03 | Sản phẩm nào đóng góp sales/profit; tập trung vào một số mã và thay đổi mix có đáng chú ý không? | Rà danh mục và nhóm ưu tiên; không tự kết luận đặt thêm tồn kho | Quantity, sales/profit share, margin; product/category/time | mart_product_performance | Q3, Q12 |
| P1 · B04 | Sales/profit thay đổi theo thời gian thế nào, nhóm nào đóng góp phần thay đổi? | Chọn market/segment/category cần drill-down | Monthly sales/profit, order count, AOV; YoY khi đủ kỳ | mart_monthly_performance | Q11 + facts |
| P2 · B05 | Giá trị mua tập trung ở khách nào; nhóm mua nhiều nhưng lâu chưa quay lại là ai? | CRM xây danh sách ưu tiên đánh giá theo rule | RFM, observed repeat purchase, cohort/window đủ quan sát | mart_customer_rfm; customer history | Q4, Q8, Q13, Q14 |
| P2 · B06 | Có tập sản phẩm mua cùng đủ dữ liệu và đáng thử bundle không? | Đề xuất bundle hypothesis để kiểm chứng | Multi-product orders, pair count/support/confidence/lift | Order-products bridge, mart_market_basket khi đủ điều kiện | Q9, Q15 |

Các câu hỏi trên là hướng kiểm tra, chưa khẳng định có nhóm margin thấp, có discount gây lỗ hoặc có combo hiệu quả. Những yếu tố như tồn kho, CAC, logistics, giá đối thủ chưa có nên không kết luận ROI hoặc tối ưu danh mục toàn diện.

## 4. Metric framework tối thiểu

Ba KPI đầu ra đề xuất, chỉ dùng trong phạm vi có đơn vị/semantic tương thích:

| KPI | Định nghĩa dự kiến | Giá trị và giới hạn |
| --- | --- | --- |
| Source-reported profit | SUM(profit) ở grain sales line | Đo đóng góp tuyệt đối; chưa gọi net profit khi chưa rõ chi phí |
| Profit margin | SUM(profit) / NULLIF(SUM(sales), 0) | Kiểm chất lượng sales; không AVG margin theo dòng hoặc theo nhóm |
| Source-reported sales | SUM(sales) ở grain sales line | Đo quy mô; không tối ưu một mình khi profit/margin xấu đi |

Driver dùng khi drill-down: số order keys hợp lệ và AOV = sales/order count; quantity/product mix; discount theo dòng hoặc bucket đã chốt. Không suy ra gross sales, cost, incremental sales do promotion hoặc LTV dự báo từ các trường hiện có.

Guardrails: loss-order rate = số đơn có tổng profit < 0 / số đơn hợp lệ; coverage của dimension lookup/null và phần sales/profit chưa phân loại. Loss-order rate phải tính sau order roll-up, không lấy số dòng profit âm làm số đơn lỗ. Unknown product/region vẫn thuộc tổng và được công bố riêng.

Chưa đặt targets kinh doanh: cần baseline, kỳ so sánh và người quyết định trước. Đây là metric design, không phải kết quả KPI hoặc lời khuyên đầu tư thực tế.

## 5. Metric contract trước mỗi câu trả lời

Mỗi metric/analysis cần ghi đủ bảng dưới; chưa có thông tin thì đánh dấu **open/provisional**, không tự điền giả định vào model như sự thật:

| Trường | Phải làm rõ |
| --- | --- |
| Question / decision | B-ID, Q-ID nếu có; ai giả định sẽ xem xét quyết định gì |
| Definition | Công thức, numerator/denominator; ratio of sums hay average; sales/profit semantics |
| Population / grain | Lines, orders, customers hay pairs; eligibility và exclusions có audit |
| Units / dimensions | Currency, discount scale; market/segment/category có mapping nào |
| Time | Window, full/partial periods, comparison, as_of_date; chưa tự dùng ngày hôm nay cho dataset lịch sử |
| Null / unknown | Cột nào required, cột nào được null; phần chưa match dimension/missing money đóng góp bao nhiêu |
| Evidence / ownership | Source/model/SQL, extraction_id, analysis_run_id, code hash/revision; rule được ai/giả định nào chốt |
| Decision limits | Điều gì có thể kết luận, điều gì chỉ là giả thuyết; cách kiểm chứng tác động |

Không gọi tổng tài chính của đơn có thiếu giá trị tiền là hoàn chỉnh chỉ vì SUM bỏ qua null. Nếu chưa chốt missing-money policy thì block metric liên quan hoặc công bố rõ population hợp lệ và phần không đánh giá được. Customer count toàn bộ dimension khác buyer count; revenue của buyer khác tất cả đăng ký trong customer.

## 6. Điều kiện nghiệm thu theo câu hỏi

| Nhóm | Phân tích tối thiểu | Điều kiện đủ để trình bày | Bước xử lý khi thiếu điều kiện |
| --- | --- | --- | --- |
| B01 | Totals → market/segment/category; sales cùng profit/margin; đơn lỗ sau roll-up | Money semantics/currency scope; line/order grain; unknown coverage và totals khớp | Chỉ báo source-reported values trong scope xác định; giữ order metrics provisional |
| B02 | Discount distribution/buckets trong cùng category/segment/kỳ; margin/loss rate | Discount scale và null policy; nhóm so sánh cùng scope; đủ sample | Profiling trước; không tự nhân sales với 1-discount hoặc tuyên bố causal uplift |
| B03 | Product/category contribution, concentration và thay đổi mix | Product identity, distinct keys, quantity/sales/profit share đối soát được | Báo theo source product_code với caveat; không gộp mã chỉ vì trùng tên |
| B04 | Monthly change, contribution của từng nhóm; YoY khi đủ baseline | Calendar spine, full/partial period flags, đúng tháng năm trước và currency scope | Trả YoY null nếu thiếu baseline hoặc denominator không hợp lệ; không coi thiếu dữ liệu là 0 |
| B05 | Observed repeat và RFM tại một as-of/window cố định | Order scope, thời gian quan sát, eligibility, ties/scoring và inactivity rule | Ghi rule-based risk; không gọi là churn thật hoặc predicted LTV |
| B06 | Multi-product orders, pair count/support/confidence/lift | Distinct product/order, population gồm đơn một sản phẩm hợp lệ; minimum count/support đã chốt | Giữ ở hypothesis; không suy lift > 1 thành hiệu quả bundle đã chứng minh |

Các kiểm tra business này được cụ thể hóa thành test matrix trong [plan raw → Gold](raw-to-gold.md#tests). Không ép tạo mart riêng cho từng query. Dashboard chỉ là kênh trình bày các metric đã có contract và evidence.

## 7. Quy tắc giữ chất lượng kết luận

- Unique/not-null tại đúng grain; không ép order_id unique ở sales line hoặc gộp product theo tên.
- Giữ toàn bộ sales orphan, LEFT JOIN và công bố unknown/null coverage; baseline product=2/region=2 là số dòng kỹ thuật, không phải ngưỡng cố định cho mọi snapshot.
- Sau joins và roll-up phải đối soát keys/counts/totals. Không MIN/MAX một header xung đột để che lỗi order grain.
- Monthly dùng cùng kỳ/đơn vị; RFM dùng fixed as-of/window, nêu right-censoring khi so cohorts; basket không self-pair và không nhân count theo quantity.
- PII không xuất nguyên rows/email/tên vào reports public hoặc dashboard chỉ cần aggregates.
- Không chọn target KPI, churn window, discount threshold hoặc basket support tùy ý rồi coi là chuẩn business. Ghi căn cứ và sensitivity nếu dùng rule học tập.

## 8. Mẫu insight và evidence

```text
Business question: B-ID / Q-ID và quyết định cần hỗ trợ
Observation: metric + đơn vị + kỳ + population + comparison
Evidence: model/grain, SQL path, extraction_id, code/run metadata
Materiality: quy mô tuyệt đối, tỷ trọng, độ phủ/đủ mẫu
Interpretation: giải thích có thể, alternative explanations
Action: đề xuất ai xem xét việc gì; chưa gọi là tác động đã chứng minh
Validation: thêm dữ liệu hoặc thử nghiệm nào để xác nhận giả thuyết
Limitations: currency, cost scope, missing keys, thời gian quan sát
```

Ví dụ **câu hỏi**, không phải kết quả: “Trong cùng category/segment/kỳ, nhóm discount cao có margin và loss-order rate khác nhóm còn lại như thế nào?”. Nếu khác, kiểm product mix/selection effects trước khi đề xuất thử thay đổi discount. Quan sát chưa chứng minh quan hệ nhân quả.

Đầu ra hướng tới 3–5 phát hiện có bằng chứng; ít hơn nếu chưa đủ dữ liệu. Mỗi phát hiện có SQL có thể chạy lại, scale/coverage, caveat, hành động đề xuất và cách kiểm chứng. Không ép đủ số lượng insight.

## 9. Phạm vi và thứ tự ưu tiên

1. Chốt open definitions ở mục 2; hoàn thiện raw/Bronze tests và Silver contracts theo plan kỹ thuật.
2. Xây facts line/order vừa đủ, trả B01/B02 bằng analyses; monthly/product marts cho B03/B04 khi dùng lại.
3. Viết báo cáo evidence; sau đó Streamlit đọc Gold release đã kiểm. Airflow/CDC mở rộng theo nhu cầu học sau P1.
4. B05/B06 khi đủ observation window, product/order identity, scoring và support rules.

Dataset hiện không có ad spend, clickstream/funnel, inventory, returns hoặc cost breakdown đầy đủ. Không suy CAC/ROAS, conversion, stock-out, return rate, nguyên nhân churn hoặc ROI toàn diện từ bốn bảng này.

## 10. Nguồn, bằng chứng và điểm còn mở

- Nguồn bài tập: [Xóm E-Com](https://dataset.xomdata.com/datasets/schema/e_commerce); [Q01–Q15](../context.md) là query backlog chi tiết.
- [Data modeling](../data-modeling.md) ghi grain/metrics; [architecture](../architecture.md) mô tả thành phần. [Plan raw → Gold](raw-to-gold.md) là đầu mối implementation, test matrix và records kiểm chứng.
- Source types/keys ở [table_contracts.py](../../ingestion/sources/table_contracts.py), Bronze SQL ở dbt/models/bronze. Trạng thái được đối chiếu với code/records local, không phải đọc lại warehouse hay chạy phân tích kinh doanh ngày 25/10.
- Stakeholders, operating cadence và mục tiêu kinh doanh là giả định học tập; chưa phỏng vấn stakeholder, chưa xác nhận currency/sales/profit semantics ngoài nguồn, chưa đặt targets hoặc chứng minh tác động.

Hai plan này thay thế các plan rời theo ngày; evidence kỹ thuật cũ đã gộp vào raw-to-gold để không mất dấu các lần chạy.
