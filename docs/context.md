# Business context và 15 câu hỏi

Nguồn controlling: [Xóm E-Com business context](https://dataset.xomdata.com/datasets/schema/e_commerce). Danh sách dưới đây chuyển thể 15 tiêu đề câu hỏi trên trang nguồn; định nghĩa chi tiết là đề xuất của dự án, cần xác nhận bằng profiling và yêu cầu nghiệp vụ.

## Phạm vi

Marketplace nhiều thị trường với danh mục Office Supplies, Furniture và Technology. Trọng tâm phân tích: doanh thu/lợi nhuận, chiết khấu, phân khúc khách hàng, địa lý và mua lặp lại.

Chưa có business insights được tính/đối soát; inventory và kết quả kỹ thuật loader không phải kết luận kinh doanh. Các số trong business narrative của website không phải kết quả pipeline đã đối soát. Không đưa kết luận về traffic, ad spend, return rate, Mr. Fuzzy hay Sugar Panda vào báo cáo của dataset này.

## Cách dùng bộ câu hỏi

[Plan dbt + commercial analytics](plans/business-questions.md) là hướng ưu tiên hiện tại. Gom câu hỏi thành B01 hiệu quả/lỗ, B02 discount, B03 product mix, B04 xu hướng, B05 khách hàng và B06 basket. Mỗi nhóm phải nêu quyết định cần hỗ trợ, metric/grain, model/test, evidence và giới hạn; 15 query dưới đây là bộ công cụ, không phải 15 insight.

Các câu hỏi cần hỏi nguồn/người quyết định trước: sales gross/net, cost scope của profit, currency, scope order_id, product-code identity, kỳ so sánh và định nghĩa VIP/inactivity/support. Các vai trò Finance/Commercial/CRM trong plan là giả định học tập. Không coi chúng là yêu cầu stakeholder đã được xác nhận.

## Câu hỏi và đầu ra dự kiến

| ID | Câu hỏi | Nguồn model dự kiến | Quy ước cần chốt |
| --- | --- | --- | --- |
| Q1 | Tổng doanh thu và lợi nhuận | `fct_order_lines` | Kỳ phân tích; semantic sales/profit |
| Q2 | Doanh thu theo segment | `fct_order_lines` | Segment tại giao dịch; xử lý null |
| Q3 | Top 10 sản phẩm bán chạy | `mart_product_performance` | Xếp theo quantity hay sales; đề xuất quantity |
| Q4 | Số khách theo gender × occupation | `dim_customers` | Toàn bộ khách hay chỉ người đã mua; null buckets |
| Q5 | Discount trung bình theo category | `fct_order_lines`, `dim_products` | AVG theo dòng hay trọng số; thang discount |
| Q6 | Profit margin theo market | `fct_order_lines`, `dim_regions` | Ratio of sums; doanh thu bằng 0 |
| Q7 | Số đơn lỗ theo segment | `fct_orders` | Profit tổng đơn < 0; segment nhất quán |
| Q8 | Khách VIP có nguy cơ churn | `mart_customer_rfm` | VIP, inactivity threshold, as-of; cờ theo quy tắc |
| Q9 | Cross-sell Consumer so với Corporate | `fct_orders`, `fct_order_lines` | Đề xuất so tỷ lệ đơn đa category; xác nhận lại cách hiểu cross-sell |
| Q10 | Top 15 quốc gia theo doanh thu | `fct_order_lines`, `dim_regions` | Country mapping; kỳ và tie-break |
| Q11 | Tăng trưởng doanh thu YoY theo tháng | `mart_monthly_performance` | Tháng đủ kỳ; calendar spine; thiếu baseline |
| Q12 | Top 3 sản phẩm lợi nhuận cao nhất mỗi category | `mart_product_performance`, `dim_products` | Tổng profit hay margin; đề xuất tổng profit |
| Q13 | Khách mua trên nhiều region | `fct_order_lines`, `dim_regions` | Region theo giao dịch, không phải nơi ở của customer |
| Q14 | Phân khúc khách hàng bằng RFM | `mart_customer_rfm` | Cửa sổ, as-of, scoring, tie policy và segment rules |
| Q15 | Sản phẩm thường mua cùng | `mart_market_basket` | Product-code identity; minimum support/count; kỳ |

Một câu hỏi có thể được trả lời bằng SQL trong `dbt/analyses/`; không cần tạo riêng một mart cho từng câu. File analysis Q01–Q15 sẽ được viết sau khi các contract được xác nhận.

## Metadata cho mỗi câu trả lời

- Nguồn model và grain; tập dữ liệu được đưa vào/loại ra.
- Ngày bắt đầu/kết thúc, `as_of_date` nếu có, `extraction_id`, `analysis_run_id`, `release_id` và code revision/hash.
- Định nghĩa metric, đơn vị và quy tắc null/ties.
- SQL có thể chạy lại và các phép đối soát liên quan.
- Phân biệt quan sát, giả thuyết và đề xuất hành động.

## Các quyết định còn mở

1. `sales` trước hay sau discount; `profit` bao gồm khoản chi phí nào; đơn vị tiền tệ có nhất quán không?
2. `row_id`, `order_id` và các dimension codes có unique ở scope mong muốn không?
3. Cùng product code có thuộc tính xung đột không, và có thể coi là một SKU không?
4. Có đơn thiếu customer/product/region, ngày hoặc giá trị tài chính không?
5. Định nghĩa VIP, churn-risk, cửa sổ RFM và cross-sell được chọn là gì?

Chỉ chốt ngưỡng và kết luận sau khi truy vấn dữ liệu thật. Khi thiếu lịch sử quan sát, không gọi RFM monetary là lifetime value dự báo.

## Thứ tự tạo giá trị

Bắt đầu Q1/Q2/Q5/Q6/Q7 để kiểm tra sales, margin và đơn lỗ, rồi Q3/Q10/Q11/Q12 cho sản phẩm/thị trường/thời gian. Q4/Q13/Q14 dùng dimensions và order grain đã kiểm tra; Q8 cần chốt rule VIP/risk. Q9/Q15 làm sau product identity và basket population. Không cần tạo một mart cho mỗi câu hỏi.

Đầu ra MVP là SQL có thể chạy lại cùng báo cáo 3–5 phát hiện. Mỗi phát hiện gồm số liệu, kỳ, phạm vi, tác động kinh doanh, hành động đề xuất và giới hạn. Nếu thiếu currency contract hoặc không có baseline/đủ support thì ghi chưa đủ điều kiện kết luận. Dashboard và chatbot không phải điều kiện hoàn thành báo cáo.
