# Commercial analytics

SQL có thể chạy lại nằm trong warehouse/analyses/; báo cáo diễn giải kinh doanh đã rà soát nằm trong analysis/reports/. Dữ liệu export, charts nháp hoặc artifacts có PII nằm trong vùng local được ignore, không commit vào đây.

Mỗi báo cáo ghi câu hỏi, grain, population, kỳ, định nghĩa metric/đơn vị, extraction_id/analysis_run_id/release_id và query nguồn. Trình bày phát hiện, quy mô ảnh hưởng, hành động đề xuất và giới hạn; không nhầm tương quan với nguyên nhân.

Ưu tiên sales/profit/margin/loss orders, product và monthly trends, rồi RFM/basket khi đủ contract. Chưa có báo cáo hoặc insight được tính. [15 câu hỏi](../docs/context.md), [grain và metrics](../docs/data-modeling.md).
