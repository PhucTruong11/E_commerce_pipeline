# Xóm E-Com · Commercial Analytics with dbt

Dự án học **dbt và tư duy phân tích kinh doanh** từ dữ liệu bán hàng Xóm E-Com: làm rõ sales/profit, tìm nhóm cần điều tra về margin và đơn lỗ, phân tích discount/product mix, rồi mở rộng sang khách hàng.

Mỗi đầu ra đi theo một chuỗi có thể kiểm chứng: **câu hỏi business → định nghĩa metric và grain → dbt models/tests → SQL và bằng chứng → insight, hành động đề xuất và cách kiểm chứng**.

**Trạng thái 24/10/2026:** Docker và luồng CSV → PostgreSQL → DuckDB raw đã chạy; 4 dbt Bronze views đã build và đối soát đủ 100.889 dòng với raw. **dbt data tests, Silver/Gold, business analyses và báo cáo insight chưa triển khai.** Xem [Bronze review](docs/plans/raw-to-gold.md#evidence). Các câu hỏi và outputs dưới đây là mục tiêu của dự án.

## Những vấn đề kinh doanh cần làm rõ

| Ưu tiên | Câu hỏi | Quyết định được hỗ trợ |
| --- | --- | --- |
| B01 · Hiệu quả/lỗ | Sales và profit nằm ở đâu? Nhóm nào sales lớn nhưng margin thấp; đơn lỗ tập trung ở đâu? | Chọn market/segment/category cần điều tra trước |
| B02 · Discount | Trong các nhóm tương đương, discount cao đi cùng margin/loss-order rate như thế nào? | Rà pricing/promotion và chọn giả thuyết cần kiểm chứng |
| B03 · Product mix | Sản phẩm nào đóng góp quantity, sales và profit; mức tập trung và mix thay đổi ra sao? | Rà danh mục và nhóm ưu tiên phân tích |
| B04 · Xu hướng | Sales/profit thay đổi theo kỳ thế nào; nhóm nào đóng góp phần thay đổi? | Chọn nhánh drill-down, tránh nhìn tổng mà bỏ qua mix |
| B05 · Khách hàng, sau P1 | Khách giá trị cao nhưng lâu chưa quay lại là ai, theo rule/cửa sổ nào? | Xây nhóm CRM ưu tiên đánh giá |
| B06 · Basket, sau P1 | Có cặp sản phẩm mua cùng đủ support để đề xuất thử bundle không? | Đặt giả thuyết cross-sell, chưa khẳng định bundle hiệu quả |

Business roles trong plan là giả định học tập. Chưa có nghiên cứu xác nhận discount gây lỗ, churn thực tế hoặc tác động của một hành động kinh doanh. Xem [business questions và metric framework](docs/plans/business-questions.md), [15 query hỗ trợ](docs/context.md).

## Từ dữ liệu tới bằng chứng

![Business questions, dbt models, tests và evidence; raw và Bronze views đã có; tests, Silver/Gold đang lên kế hoạch](docs/diagrams/data-flow.svg)

Luồng dữ liệu hiện tại: **CSV bootstrap → PostgreSQL source → Python consistent snapshot → DuckDB raw → dbt Bronze views**. Phần tiếp theo: **dbt tests → Silver → Gold → analyses/báo cáo**. dbt biến đổi dữ liệu trong DuckDB; PostgreSQL giữ nguồn, Docker đóng gói môi trường chạy.

Tests bảo vệ kết luận: đúng grain, không mất hoặc nhân dòng khi join, totals khớp xuyên lớp, unknown/null coverage được công bố. Một lần dbt debug thành công chưa chứng minh metric hoặc insight đúng.

## dbt phục vụ từng đầu ra thế nào?

| Lớp / đường dẫn | Vai trò | Trạng thái |
| --- | --- | --- |
| `dbt/models/raw/` | Khai báo 4 bảng Python đã nạp; source docs/tests và lineage | Có raw source declarations; mở rộng tests tiếp theo |
| `dbt/models/bronze/` | Explicit source projections, giữ grain/values/lineage bằng dbt views | 4 views + lineage macro đã kiểm; dbt data tests chưa triển khai |
| `dbt/models/silver/` | Staging, chuẩn hóa có quy tắc, LEFT JOIN, unknown flags và order grain | Models đang plan |
| `dbt/models/gold/` | Facts line/order, monthly/product marts; RFM/basket sau khi đủ điều kiện | Models đang plan |
| `dbt/analyses/` | SQL trả lời business questions và drill-down | Chưa có analyses; dbt build không tự thực thi chúng |
| `analysis/reports/` | Phát hiện, evidence, tác động/quy mô, hành động đề xuất và giới hạn | Chưa có báo cáo |

Mốc gần nhất là [Raw/Bronze tests → Silver → Gold](docs/plans/raw-to-gold.md), rồi `fct_order_lines` và `fct_orders`. B01/B02 có thể dùng facts + analyses; chỉ tạo mart riêng khi có nhu cầu dùng lại. Ưu tiên monthly/product trước RFM/basket.

![Grain và models dự kiến gắn với từng nhóm câu hỏi business](docs/diagrams/model-flow.svg)

Đầu ra phân tích hướng tới 3–5 phát hiện có bằng chứng, hoặc ít hơn nếu dữ liệu chưa đủ. Mỗi phát hiện ghi metric/đơn vị/kỳ/population, model/SQL, extraction/code/run metadata, quy mô ảnh hưởng và cách kiểm chứng giả thuyết.

## Dataset và điều kiện diễn giải

Nguồn: [Xóm E-Com](https://dataset.xomdata.com/datasets/schema/e_commerce). Baseline local đã kiểm:

| Nguồn | Dòng | Grain |
| --- | ---: | --- |
| customer | 17.415 | Một customer_id |
| product | 28.356 | Một product_code; chưa mặc định là SKU nghiệp vụ |
| region | 3.828 | Một region_code |
| ecom_sales | 51.290 | Một row_id, không phải một order |

Tổng 100.889 dòng, khoảng 8,76 MiB. Baseline có 2 dòng sales không khớp product và 2 không khớp region; các tập có thể chồng nhau. Source/raw giữ nguyên; Bronze cần bảo toàn chúng; Silver cần LEFT JOIN và báo unknown coverage.

Trước khi diễn giải tài chính phải chốt **sales trước/sau discount, cost scope của profit và currency**. Trước AOV/đơn lỗ/RFM/basket phải xác nhận order key và product identity. Không suy ra CAC/ROAS, conversion funnel, returns, stock-out hoặc nguyên nhân churn từ bốn bảng hiện có.

Quy tắc metric/grain chi tiết nằm trong [data modeling](docs/data-modeling.md). Discount impact ở đây là phân tích quan sát; RFM risk là cờ theo rule.

## Nền kỹ thuật đã có

![Kiến trúc PostgreSQL, Python, DuckDB, dbt, Docker và shared Airflow; phân biệt phần đã chạy với phần dự kiến](docs/diagrams/architecture.svg)

Sơ đồ thể hiện Docker runtime chứa Python/DuckDB/dbt; PostgreSQL và Airflow thuộc platform dùng chung. **Luồng đã chạy tới 4 Bronze views**; dbt data tests, Silver/Gold, publication và DAG là bước tiếp theo. [Ảnh PNG](docs/diagrams/architecture.png) · [SVG có thể chỉnh sửa](docs/diagrams/architecture.svg) · [Nguồn logo](docs/diagrams/tech-logos.json).

- **PostgreSQL + Python:** bootstrap 4 CSV và ledger trong transaction; retry baseline trả skipped; extractor đọc một snapshot nhất quán qua reader riêng.
- **DuckDB + Docker:** candidate/file/volumes riêng, precision và lineage; đối soát hash/counts/nulls/totals, mở lại read-only. Image đã build lại và 12 synthetic integration checks đã đạt ngày 24/10/2026.
- **Bước sau:** bổ sung source/model data tests cho Bronze đã viết, rồi Silver/Gold; đường chạy dbt có guard/lock/resource budget; Gold publication trước serving liên tục. DAG Airflow, CDC và dashboard là backlog sau các mốc phân tích đầu.

Các kiểm tra ingestion là evidence kỹ thuật, chưa phải business findings. Kiến trúc hiện tại phục vụ mục tiêu học tách source/analytics, chưa có benchmark chứng minh vượt trội về hiệu năng. Không thêm service vào chặng phân tích chỉ để tăng số công cụ.

## Bắt đầu và tài liệu

Hai plan chính: **business questions** để chọn trọng tâm, **raw → Gold** để thực hành theo contracts và tests. Records bootstrap/extract/Bronze review đã được gộp trong plan kỹ thuật.

| Mục tiêu | Đọc |
| --- | --- |
| Định hướng business → metrics → dbt → insight | [Business questions và metric contracts](docs/plans/business-questions.md) |
| Thứ tự triển khai, clean, macros/tests và checkpoint | [Plan raw → Gold](docs/plans/raw-to-gold.md) |
| Câu hỏi, định nghĩa và điều kiện kết luận | [Business context](docs/context.md), [data modeling](docs/data-modeling.md) |
| Tiến độ và checkpoint | [Roadmap](docs/roadmap.md) |
| Setup/check runtime, PostgreSQL/DataGrip | [Docker runbook](docs/docker.md) |
| Thành phần, flow, writer và recovery | [Architecture](docs/architecture.md) |
| Mở rộng sau các mốc phân tích | [Airflow](docs/airflow-docker.md), [CDC](docs/cdc-plan.md) |

Máy maintainer dùng shared platform theo [AGENTS.md](AGENTS.md); người clone cần platform/credentials và CSV của riêng mình theo runbook. Chưa có Compose standalone hoặc quickstart end-to-end cho người chưa có platform.

CSV, secrets, DuckDB files và runtime artifacts không commit/bake vào image. `.local/secrets/` chứa mật khẩu đang dùng; bản `.local/datagrip/` là inspection snapshot private, không tự cập nhật hoặc thay cho Gold serving release.
