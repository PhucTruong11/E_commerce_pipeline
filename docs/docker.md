# Chạy môi trường e-commerce bằng Docker

**Môi trường dev đã được triển khai ngày 2026-10-24.** Có runtime Python + psycopg + DuckDB + dbt-duckdb, database/users riêng trên PostgreSQL chung và các lệnh kiểm tra bên dưới. Hai loader đã build, qua 10 kiểm tra fixture và chạy dữ liệu thật thành công: 100.889 dòng PostgreSQL → DuckDB Bronze, retry bootstrap skipped. Chưa có models/insight hoặc DAG; `dbt debug` chỉ kiểm tra môi trường, không chứng minh pipeline đã chạy.

## 1. Hiểu đúng thành phần đang dùng

```mermaid
flowchart LR
    CSV[4 CSV local<br/>mount chỉ đọc] --> R[Container ecom-runtime<br/>chạy theo lệnh rồi tự xóa]
    R -->|ecom_reader: đọc nguồn| PG[(PostgreSQL dùng chung<br/>DB ecom_source_dev)]
    O[Owner runtime<br/>chỉ dùng khi bootstrap] -->|ecom_owner: ghi nguồn| PG
    R --> B[(ecom-dev-build<br/>DuckDB candidate + writer lock)]
    R --> A[(ecom-dev-artifacts<br/>logs và báo cáo kiểm tra)]
    R --> G[(ecom-dev-releases<br/>dành cho Gold publish sau này)]
    AF[Airflow dùng chung<br/>chưa tích hợp DAG ecom] -.-> R
```

Không có DuckDB server, MinIO hay PostgreSQL container mới. `compose.shared.yaml` dùng network `laplaptech-lab` và warehouse hiện có. Build image không nạp CSV hoặc secrets vào image. Hai service `runtime` và `owner` dùng cùng image nhưng chỉ được mount mật khẩu đúng vai trò; mặc định dùng reader.

| Thành phần | Cấu hình |
| --- | --- |
| Image | `ecom-runtime:local-v1`, Python base ghim digest; dependencies trong `requirements.lock.txt` |
| Runtime | 1024 MiB RAM, 1 CPU, 256 PID, không swap; chạy user 10001, root filesystem chỉ đọc |
| DuckDB/dbt | 512 MB memory, 1 thread, spill tối đa 1 GB trong build volume |
| PostgreSQL source | `ecom_source_dev`; schemas `e_commerce`, `pipeline_meta` |
| Owner / reader | `ecom_owner` / `ecom_reader`, đều không có quyền admin; connection limit 4 / 2 |
| Credentials | `.local/secrets/owner.password`, `.local/secrets/reader.password`, không commit |
| Resource policy | `projects.ecom.tasks.refresh`: 1024 MiB/1 CPU, 2 slot trong pool chung; chưa có DAG sử dụng |

## 2. Bật PostgreSQL nguồn

Mở Docker Desktop trước. Với platform trên máy maintainer, chỉ bật warehouse:

```powershell
Set-Location 'D:\Dev\Project\airflow-platform'
docker compose --env-file .env -f compose.yaml -f compose.laplaptech.yaml up -d --no-deps warehouse-laplaptech
docker compose --env-file .env -f compose.yaml -f compose.laplaptech.yaml ps warehouse-laplaptech
```

Chờ `healthy`. Các lệnh CLI môi trường yêu cầu **shared scheduler đang tắt** để tránh Airflow đồng thời nhận job ngoài cửa sổ kiểm tra thủ công. Không tắt một platform đang có task của project khác: dùng Manager để drain/off trước khi chuyển sang cửa sổ CLI. Khi tích hợp DAG sau này, dùng `BudgetDockerOperator`; không cần tắt scheduler để chạy qua Airflow.

Người clone chưa có platform phải đọc quy ước của platform mình đang dùng và cấp DB/roles theo phần dưới. **Compose standalone cho người chưa có shared platform chưa được triển khai.** Không chạy bootstrap LapLapTech để ghi đè workspace chung.

## 3. Cấu hình lần đầu

```powershell
Set-Location 'D:\Dev\Project\e_commerce'
.\scripts\Initialize-LocalEnv.ps1
docker compose -f compose.shared.yaml config --quiet
```

Script tạo root `.env` từ mẫu và sinh hai mật khẩu ngẫu nhiên riêng. Chạy lại giữ nguyên file và mật khẩu hiện có. Không cần activate venv hoặc cài Python packages trên Windows. Các script dùng PowerShell 7 và Docker CLI.

Trên máy này database/roles đã được cấp. Khi setup một shared warehouse mới tương thích, admin chạy **một lần**, sau khi kiểm tra đúng target:

```powershell
.\scripts\Provision-SharedSource.ps1
```

Script quản trị này khóa vào container/role admin hiện tại của platform, kiểm PostgreSQL 16 và database `postgres`, rồi tạo database/roles riêng nếu **tất cả đều chưa tồn tại**. Nó không reset password hoặc xóa DB có sẵn; trạng thái tạo dở phải được kiểm tra trước khi thử lại. Runtime không nhận credential admin. Script tạo hai schema rỗng và default privilege SELECT cho bảng do owner tạo trong `e_commerce`; không tạo bốn bảng nghiệp vụ. Reader không được ghi nguồn hoặc truy cập `pipeline_meta`.

Khi thêm máy khác, điều chỉnh phần admin target có chủ đích theo contract của platform đó. Trong registry vận hành phải có entry `ecom/refresh` theo [mục 7](#7-registry-ecom); wrapper sẽ từ chối nếu chưa đăng ký.

## 4. Build và kiểm tra

```powershell
Set-Location 'D:\Dev\Project\e_commerce'
$ecomPlatformDir = 'D:\Dev\Project\airflow-platform'
.\scripts\Invoke-Dev.ps1 -Action Build -PlatformDir $ecomPlatformDir
.\scripts\Invoke-Dev.ps1 -Action Versions -PlatformDir $ecomPlatformDir
.\scripts\Invoke-Dev.ps1 -Action Check -Role reader -PlatformDir $ecomPlatformDir
.\scripts\Invoke-Dev.ps1 -Action Check -Role owner -PlatformDir $ecomPlatformDir
.\scripts\Invoke-Dev.ps1 -Action DbtDebug -PlatformDir $ecomPlatformDir
```

`Invoke-Dev.ps1` đọc registry thật, kiểm scheduler đang tắt, giới hạn của container đang chạy và phần RAM còn lại, rồi chạy Compose với đúng resource cap. Đây là kiểm tra tại thời điểm bắt đầu: không đồng thời bật stack hoặc chạy writer khác trong cửa sổ CLI. Docker BuildKit có tiến trình build riêng; phép tính này không phải trần RAM riêng cho từng bước build. Build khi các project nặng đang tắt, như lần triển khai ban đầu.

`Check` xác thực mật khẩu qua TCP, đúng database/user, role không có quyền admin, schema ACL; thử ghi/đọc DuckDB và các volume bằng dữ liệu tổng hợp rồi xóa file thử. Nó không đọc/in các dòng khách hàng. Trước bootstrap có `source_tables: 0`, sau bootstrap thành công phải có 4 bảng. `input_files_present: false` nghĩa thiếu CSV local, không phải PostgreSQL lỗi.

`DbtDebug` dùng DuckDB tạm trong build volume và profile thật; thành công có `All checks passed`. Không có models nên chưa chạy `dbt run/build/test/freshness` cho pipeline. Bootstrap/Extract đã dùng file lock `.writer.lock`; runner refresh sau này phải giữ lock xuyên các stage; sau extract phải đóng DuckDB trước khi gọi dbt.

Report cuối lưu trong volume `ecom-dev-artifacts` tại `environment-latest.json`. `dbt debug` có log theo lần chạy; kiểm tra và dọn artifacts đúng project theo nhu cầu, không có retention tự động. Input CSV và file report không được bake vào image.

## 5. Bật/tắt và kiểm tra nhanh

```powershell
Set-Location 'D:\Dev\Project\e_commerce'
docker compose -f compose.shared.yaml ps -a
```

Runtime dùng `run --rm`, kết thúc là container tự xóa; không cần giữ Python/dbt chạy ngầm. Không dùng `docker compose up -d` để duy trì job môi trường. PostgreSQL chung vẫn chạy và có thể phục vụ project khác; chỉ dừng warehouse khi đã xác nhận mọi consumer của nó đều ngừng. Không dùng `down -v` để tắt: named volumes chứa state của project.

Đăng nhập bằng DataGrip/DBeaver từ Windows:

| Trường | Giá trị |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `WAREHOUSE_HOST_PORT` từ `.env` platform, hiện `55434` |
| Database | `ecom_source_dev` |
| User | `ecom_owner` để bootstrap; `ecom_reader` để đọc |
| Password | Đọc đúng file local của role trong `.local/secrets/` trên máy mình |

Nếu báo sai mật khẩu, dùng lại file secret đã provision. Sửa `.env` hoặc sinh file secret mới không tự đổi mật khẩu trong volume PostgreSQL. Không xóa volume hay reset tài khoản của project khác để chữa lỗi đăng nhập.

### Mở DuckDB bằng DataGrip

DuckDB ở đây là database file, không có host/port/user/password như PostgreSQL. Bản đã xuất cho Windows:

`D:\Dev\Project\e_commerce\.local\datagrip\ecom_analytics.duckdb`

1. DataGrip → **New → Data Source → DuckDB**; chọn kiểu kết nối bằng file.
2. Chọn file trên; tải driver **org.duckdb:duckdb_jdbc:2.0.0** để khớp runtime.
3. Trong Advanced đặt `duckdb.read_only=true`, `memory_limit=512MB` và `threads=1`. Có thể bật thêm Options → Read-only. Không dùng tài khoản PostgreSQL cho DuckDB.
4. Test Connection; trong Schemas chọn **bronze** rồi Apply/OK.

JDBC URL tương đương cho driver 2.0.0 (Connection type: URL only):

```text
jdbc:duckdb:D:/Dev/Project/e_commerce/.local/datagrip/ecom_analytics.duckdb;duckdb.read_only=true;memory_limit=512MB;threads=1
```

Kiểm tra trong query console:

```sql
SELECT 'customer' AS table_name, count(*) AS row_count FROM bronze.customer
UNION ALL SELECT 'product', count(*) FROM bronze.product
UNION ALL SELECT 'region', count(*) FROM bronze.region
UNION ALL SELECT 'ecom_sales', count(*) FROM bronze.ecom_sales;
```

Bản copy đã được kiểm tra read-only và khớp hash/rows/nulls/totals của candidate: 17.415 / 28.356 / 3.828 / 51.290 dòng. Đây là snapshot phục vụ kiểm tra, **không tự cập nhật** sau lần Extract tiếp theo. Không trỏ DataGrip trực tiếp vào build volume đang có writer. Khi muốn thay bản copy, ngắt kết nối DataGrip trước và chỉ copy candidate đã đóng writer/đạt đối soát.

Mở bản copy này không cần bật Docker/PostgreSQL. Query chạy trong process DataGrip trên Windows, nên RAM của DataGrip không nằm trong giới hạn container Docker. File chứa dữ liệu khách hàng, giữ private; `.local/datagrip` đã được Git ignore. `receipt.json` cạnh file ghi extraction_id, phiên bản, checksum và counts, không có mật khẩu.

Tham khảo: [DataGrip DuckDB](https://www.jetbrains.com/help/datagrip/duckdb.html), [JDBC read-only và giới hạn tài nguyên](https://duckdb.org/docs/2.0/clients/java/connecting).

### Vì sao không thấy ecom container nhưng Docker vẫn dùng RAM?

- Container runtime ecom chỉ chạy lúc Bootstrap/Extract rồi tự xóa bằng `run --rm`; nó không chạy nền sau khi hoàn tất.
- `warehouse-laplaptech` nằm trong stack **airflow-platform** nhưng là PostgreSQL dùng chung, chứa cả database ecom_source_dev. Vì vậy ecom không có một PostgreSQL container mang tên riêng.
- Lần kiểm tra 24/10/2026: chỉ warehouse chạy, khoảng 59 MiB. Airflow và BrewLite đã dừng; không có ecom runtime còn chạy.
- RAM trong thanh trạng thái Docker Desktop gồm Docker/WSL và cache. Không dùng số vài GB đó để kết luận ecom vẫn chạy. Trần 1 GiB/container là giới hạn tối đa, không phải bộ nhớ luôn giữ sẵn.
- Máy đã có `autoMemoryReclaim=gradual` để Windows thu hồi cache dần. Dữ liệu và image trên ổ đĩa vẫn tồn tại khi container dừng; xóa file backup không giải phóng RAM của WSL.

```powershell
docker ps --format '{{.Names}} | {{.Status}}'
docker stats --no-stream
```

PostgreSQL vẫn cần chạy khi đọc nguồn hoặc extract lần mới. Chỉ dừng warehouse chung sau khi mọi consumer không còn dùng; không dùng `down -v` hoặc ép shutdown WSL để xử lý số RAM trên UI. Xem [Docker WSL memory reclaim](https://docs.docker.com/desktop/features/wsl/).

### Giữ gì trong .local?

Chỉ cần `secrets/` (hai mật khẩu đang dùng) và `datagrip/` (bản DuckDB xem local cùng receipt). Các thư mục cleanup, dependency-resolver và backup trước chỉnh sửa đã được xóa sau khi kiểm chứng hệ thống; chúng không tham gia runtime. Không xóa secrets để dọn cache; provisioning database cũ không tự tạo lại đúng mật khẩu.

## 6. Bootstrap và extract

```powershell
Set-Location 'D:\Dev\Project\e_commerce'
$ecomPlatformDir = 'D:\Dev\Project\airflow-platform'
.\scripts\Invoke-Dev.ps1 -Action Bootstrap -Role owner -PlatformDir $ecomPlatformDir
.\scripts\Invoke-Dev.ps1 -Action Extract -Role reader -PlatformDir $ecomPlatformDir
```

Bootstrap tự tạo bảng từ typed contract, COPY bốn CSV và ghi ledger trong một transaction; không chạy SQL DDL riêng. Cùng baseline chạy lại là skipped, không reset nguồn. Extract đọc một PG snapshot, ghi candidate mới và đối soát hash/counts/nulls/totals trước khi xác nhận validated_bronze.

Receipt bootstrap/extract nằm trong ecom-dev-artifacts theo run_id/extraction_id; candidate ở ecom-dev-build/candidates/extraction_id/ecom_analytics.duckdb. Không có retention tự động. Hướng dẫn code/contract, output và test: [Bootstrap → Bronze](plans/2026-10-24-bootstrap-extract.md).

```powershell
python .\tests\integration\test_ingestion.py --platform-dir $ecomPlatformDir
```

Python host chỉ cần stdlib; test dùng PostgreSQL/runtime fixture riêng, không sửa nguồn thật. Cần scheduler OFF và ngân sách fixture PG 384 MiB + runtime 1024 MiB.

Nếu thiếu secret, khôi phục đúng **file mật khẩu cũ**; không tự sinh lại mật khẩu cho DB đã provision. Wrapper dừng trước Docker khi secret là directory/missing. Không copy password vào terminal output hoặc Git.

Tiếp theo: dbt Silver/Gold, reconciliation và immutable Gold publish; sau khi refresh CLI đạt mới thêm DAG vào shared Airflow.

Tham khảo: [Compose services](https://docs.docker.com/reference/compose-file/services/), [dbt-duckdb profile](https://github.com/duckdb/dbt-duckdb), [Psycopg connections](https://www.psycopg.org/psycopg3/docs/api/connections.html).


## 7. Registry ecom

Registry vận hành đã có `projects.ecom`: `dbt_threads=1`, `services={}`, task
`refresh={"memory_mib":1024,"cpus":1}`. Task dùng hai slot trong pool chung;
không thêm service thường trực hoặc tăng pool. DuckDB nằm trong runtime, code
dbt ở `/app/dbt`, schemas là `bronze`/`silver`/`gold`; macro giữ tên schema
đúng thay vì ghép thành `silver_gold`. Bronze do extractor nạp, source YAML
chưa tạo dữ liệu.

Standalone Compose, business models/tests, Gold publication,
DAG distribution và CI còn là các bước triển khai tiếp theo theo
[roadmap](roadmap.md). Khi sửa code Python/dbt/Dockerfile, rebuild bằng Action
Build; không sửa dependencies trong runtime đang chạy hoặc dùng `.venv` TikTok.
