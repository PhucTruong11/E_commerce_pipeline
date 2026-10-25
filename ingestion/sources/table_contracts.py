"""Explicit source types. CREATE TABLE is generated from this allowlist."""
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import re

from ingestion.runtime import PipelineError, json_text
from ingestion.sources.csv_contracts import CONTRACTS, read_checked_csv

VERSION = 'ecom-source-v1'
ORDER = ('customer', 'product', 'region', 'ecom_sales')
TYPES = {
    'customer': {'birth_date':'date', 'annual_income':'numeric(20,2)'},
    'product': {},
    'region': {'country_latitude':'numeric(12,6)', 'country_longitude':'numeric(12,6)'},
    'ecom_sales': {'order_date':'date', 'quantity':'bigint', 'sales':'numeric(20,2)',
                   'discount':'numeric(9,6)', 'profit':'numeric(20,2)'},
}
REQUIRED = {'customer': {'customer_id'}, 'product': {'product_code'},
            'region': {'region_code'},
            'ecom_sales': {'row_id','order_id','order_date','customer_id','region_code','product_code','quantity'}}
SUM_COLUMNS = {'customer': ('annual_income',), 'product': (),
               'region': (), 'ecom_sales': ('quantity','sales','profit')}


def columns(table):
    return [(name, TYPES[table].get(name, 'text'), name in REQUIRED[table])
            for name in CONTRACTS[table][1]]


def schema_signature():
    return hashlib.sha256(json_text({table: columns(table) for table in ORDER}).encode()).hexdigest()


def convert(raw, kind, required):
    cleaned = raw.strip()
    if not cleaned or cleaned.lower() == 'null':
        if required:
            raise ValueError('Missing required value')
        return None
    if kind == 'text':
        return raw  # Preserve source text; never trim identifiers on only one FK side.
    if kind == 'date':
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', cleaned):
            raise ValueError('Expected ISO date')
        return date.fromisoformat(cleaned)
    if kind == 'bigint':
        number = Decimal(cleaned)
        if not number.is_finite() or number != number.to_integral_value() or not -(2**63) <= number < 2**63:
            raise ValueError('Expected signed BIGINT')
        return int(number)
    precision, scale = map(int, re.fullmatch(r'numeric\((\d+),(\d+)\)', kind).groups())
    number = Decimal(cleaned)
    with localcontext() as context:
        context.prec = 50
        if (not number.is_finite() or abs(number) >= Decimal(10)**(precision-scale)
                or number.quantize(Decimal(1).scaleb(-scale)) != number):
            raise ValueError('Numeric value would round or overflow')
    return number


def load_input(input_dir):
    datasets, files = {}, {}
    for table in ORDER:
        try:
            records, metadata = read_checked_csv(input_dir/f'{table}.csv', table)
        except (ValueError, UnicodeError) as error:
            raise PipelineError(f'Invalid CSV structure: table={table}, error={type(error).__name__}') from None
        key, headers = CONTRACTS[table]
        typed = []
        for ordinal, record in enumerate(records, start=2):
            if record[key] != record[key].strip():
                raise PipelineError(f'Key whitespace: table={table}, record={ordinal}')
            row = []
            for name, kind, required in columns(table):
                try:
                    row.append(convert(record[name], kind, required))
                except (ValueError, InvalidOperation, OverflowError):
                    raise PipelineError(f'Invalid field: table={table}, column={name}, record={ordinal}') from None
            typed.append(tuple(row))
        datasets[table] = typed
        files[table] = {'sha256': metadata['source_file_sha256'], 'rows': metadata['row_count']}
    orphan = {}
    sales_headers = CONTRACTS['ecom_sales'][1]
    for field, target in [('customer_id','customer'),('product_code','product'),('region_code','region')]:
        position = sales_headers.index(field)
        keys = {row[CONTRACTS[target][1].index(CONTRACTS[target][0])] for row in datasets[target]}
        orphan[field] = sum(row[position] not in keys for row in datasets['ecom_sales'])
    # Unknown dimension codes remain in source/raw and are reported, never dropped.
    fingerprint = hashlib.sha256(json_text({'version':VERSION, 'schema':schema_signature(),
                                          'files':files}).encode()).hexdigest()
    return datasets, files, orphan, fingerprint


class TableStats:
    def __init__(self, table):
        self.table, self.count = table, 0
        self.digest = hashlib.sha256()
        self.nulls = {column:0 for column in CONTRACTS[table][1]}
        self.sums = {column:Decimal(0) for column in SUM_COLUMNS[table]}

    def add(self, rows):
        names = CONTRACTS[self.table][1]
        with localcontext() as context:
            context.prec = 50
            for row in rows:
                self.count += 1
                self.digest.update((json_text(list(row))+'\n').encode('utf-8'))
                for name, value in zip(names, row):
                    self.nulls[name] += value is None
                    if name in self.sums and value is not None:
                        self.sums[name] += value

    def report(self):
        return {'rows':self.count, 'sha256':self.digest.hexdigest(),
                'nulls':self.nulls, 'sums':self.sums}


def validate_source_schema(pg):
    for table in ORDER:
        actual = pg.execute('''SELECT attname, format_type(atttypid,atttypmod), attnotnull
            FROM pg_attribute WHERE attrelid=to_regclass(%s) AND attnum>0
            AND NOT attisdropped ORDER BY attnum''', (f'e_commerce.{table}',)).fetchall()
        if actual != columns(table):
            raise PipelineError(f'Source missing or schema drift: table={table}; bootstrap first')
        pk = pg.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid=to_regclass(%s) AND contype='p'",
                        (f'e_commerce.{table}',)).fetchall()
        if pk != [(f'PRIMARY KEY ({CONTRACTS[table][0]})',)]:
            raise PipelineError(f'Source primary key drift: table={table}')
