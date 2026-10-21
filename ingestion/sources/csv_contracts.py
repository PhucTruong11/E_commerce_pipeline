import csv
import hashlib
import io
from pathlib import Path

CONTRACTS = {
    "customer": ("customer_id", [
        "customer_id", "first_name", "last_name", "birth_date",
        "marital_status", "gender", "email_address", "annual_income",
        "education_level", "occupation", "home_owner",
    ]),
    "ecom_sales": ("row_id", [
        "row_id", "order_id", "order_date", "customer_id", 
        "segment", "region_code", "product_code", "quantity", "sales",
        "discount", "profit", 
    ]),
    "product": ("product_code", [
        "product_code", "product", "category", "subcategory",
    ]),
    "region": ("region_code", [
        "region_code", "city", "state", "country", "country_latitude",
        "country_longitude","region", "market",
    ]),
}

def read_checked_csv(path: Path, table: str):
    key, headers = CONTRACTS[table]
    payload = path.read_bytes()
    reader = csv.reader(
        io.StringIO(payload.decode("utf-8-sig"), newline=""),
        delimiter=",",
        strict=True,
    )
    if next(reader, None) != headers:
        raise ValueError(f"{table}: unexpected CSV headers")

    records, seen = [], set()
    for record_number, values in enumerate(reader, start=2):
        if len(values) != len(headers):
            raise ValueError(f"{table}: invalid width at record {record_number}")
        row = dict(zip(headers, values))
        candidate = row[key].strip()
        if not candidate or candidate.casefold() == "null" or candidate in seen:
            # Không log nguyên row hoặc giá trị customer key.
            raise ValueError(f"{table}: invalid key at record {record_number}")
        seen.add(candidate)
        records.append(row)

    return records, {
        "table": table,
        "row_count": len(records),
        "source_file_sha256": hashlib.sha256(payload).hexdigest(),
        "schema_version": "csv-v1",
    }