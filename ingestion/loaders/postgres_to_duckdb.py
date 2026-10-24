"""Read one PG snapshot into a new, reconciled DuckDB Bronze candidate."""
import os
from pathlib import Path

import duckdb
import psycopg
from psycopg import sql

from ingestion.runtime import (PipelineError, build_lock, connection_settings,
    guard_pg_identity, run_identity, write_report)
from ingestion.sources.csv_contracts import CONTRACTS
from ingestion.sources.table_contracts import ORDER, VERSION, TableStats, columns, validate_source_schema


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def create_bronze(duck):
    duck.execute('CREATE SCHEMA bronze')
    for table in ORDER:
        fields = [f'{quoted(name)} {kind.replace("text","VARCHAR").replace("numeric","DECIMAL")} '
                  + ('NOT NULL' if required else '') for name,kind,required in columns(table)]
        fields.extend(['_extraction_id VARCHAR NOT NULL', '_extracted_at TIMESTAMPTZ NOT NULL',
                       '_source_table VARCHAR NOT NULL', f'PRIMARY KEY ({quoted(CONTRACTS[table][0])})'])
        duck.execute(f'CREATE TABLE bronze.{quoted(table)} ({",".join(fields)})')


def write_batch(duck, table, rows, extraction_id, extracted_at):
    placeholders = ','.join('?' for _ in range(len(CONTRACTS[table][1])+3))
    statement = f'INSERT INTO bronze.{quoted(table)} VALUES ({placeholders})'
    duck.executemany(statement, [tuple(row)+(extraction_id,extracted_at,f'e_commerce.{table}') for row in rows])


def extract_tables(pg, write_batch):
    # pg is autocommit=True: this block owns exactly one snapshot transaction.
    with pg.transaction():
        pg.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        guard_pg_identity(pg,'ecom_reader')
        validate_source_schema(pg)
        snapshot, started_at = pg.execute('SELECT pg_current_snapshot()::text, transaction_timestamp()').fetchone()
        tables = {}
        for table in ORDER:
            query = sql.SQL('SELECT {} FROM {} ORDER BY {} COLLATE "C"').format(
                sql.SQL(',').join(map(sql.Identifier,CONTRACTS[table][1])),
                sql.Identifier('e_commerce',table),sql.Identifier(CONTRACTS[table][0]))
            stats = TableStats(table)
            with pg.cursor(name=f'extract_{table}') as cur:
                cur.execute(query)
                while rows := cur.fetchmany(1000):
                    stats.add(rows)
                    write_batch(table,rows,started_at)
            tables[table] = stats.report()
        return snapshot, started_at, tables, source_orphans(pg)


def candidate_stats(duck, table):
    names = ','.join(map(quoted,CONTRACTS[table][1]))
    result = duck.execute(f'SELECT {names} FROM bronze.{quoted(table)} ORDER BY {quoted(CONTRACTS[table][0])}')
    stats = TableStats(table)
    while rows := result.fetchmany(1000):
        stats.add(rows)
    return stats.report()


def source_orphans(pg):
    result = {}
    for column,target in [('customer_id','customer'),('product_code','product'),('region_code','region')]:
        statement = sql.SQL('''SELECT count(*) FROM e_commerce.ecom_sales s
            WHERE NOT EXISTS (SELECT 1 FROM {} d WHERE d.{}=s.{})''').format(
                sql.Identifier('e_commerce',target), sql.Identifier(column), sql.Identifier(column))
        result[column] = pg.execute(statement).fetchone()[0]
    return result


def extract():
    settings = connection_settings('ecom_reader')
    with build_lock() as root:
        extraction_id, started_at = run_identity()
        candidate = None
        try:
            tables = {}
            with psycopg.connect(**settings, autocommit=True) as pg:
                # Check target before creating a file. This autocommitted query
                # does not establish the later data-extraction snapshot.
                guard_pg_identity(pg,'ecom_reader')
                folder = root/'candidates'/extraction_id
                if not folder.resolve().is_relative_to(root/'candidates'):
                    raise PipelineError('Unexpected candidate path')
                folder.mkdir(parents=True,exist_ok=False)
                candidate = folder/'ecom_analytics.duckdb'
                config = {'memory_limit':'512MB','threads':1,'temp_directory':str(root/'spill'/extraction_id),
                          'max_temp_directory_size':'1GB'}
                with duckdb.connect(str(candidate),config=config) as duck:
                    duck.execute('BEGIN')
                    create_bronze(duck)
                    snapshot, extracted_at, expected_tables, orphans = extract_tables(pg,
                        lambda table,rows,stamp: write_batch(duck,table,rows,extraction_id,stamp))
                    for table in ORDER:
                        actual = candidate_stats(duck,table)
                        if actual != expected_tables[table]:
                            raise PipelineError(f'Snapshot reconciliation failed: table={table}')
                        tables[table] = actual
                    duck.execute('COMMIT')
                    duck.execute('CHECKPOINT')
            # Reopen only after both writers/transactions have closed.
            with duckdb.connect(str(candidate),read_only=True) as duck:
                for table in ORDER:
                    if candidate_stats(duck,table) != tables[table]:
                        raise PipelineError(f'Reopened candidate mismatch: table={table}')
                    lineage = duck.execute(f'''SELECT count(*) FROM bronze.{quoted(table)}
                        WHERE _extraction_id IS DISTINCT FROM ? OR _extracted_at IS DISTINCT FROM ?
                        OR _source_table IS DISTINCT FROM ?''',
                        [extraction_id,extracted_at,f'e_commerce.{table}']).fetchone()[0]
                    if lineage:
                        raise PipelineError(f'Extraction lineage mismatch: table={table}')
            report = {'status':'validated_bronze', 'extraction_id':extraction_id, 'started_at':started_at,
                'snapshot':snapshot, 'extracted_at':extracted_at, 'candidate':str(candidate),
                'contract_version':VERSION, 'tables':tables, 'orphan_counts':orphans,
                'orphan_policy':'preserve_and_report'}
            report['receipt'] = write_report('extract',extraction_id,report)
            return report
        except Exception as error:
            if candidate is not None:
                candidate.unlink(missing_ok=True)
                Path(str(candidate)+'.wal').unlink(missing_ok=True)
                if not any(candidate.parent.iterdir()):
                    candidate.parent.rmdir()
            try:
                write_report('extract',extraction_id,{'status':'failed','extraction_id':extraction_id,
                    'error_type':type(error).__name__,'sqlstate':getattr(error,'sqlstate',None)})
            except (OSError,ValueError):
                pass
            if isinstance(error,PipelineError):
                raise
            raise PipelineError(f'Extraction failed: error_type={type(error).__name__}, sqlstate={getattr(error,"sqlstate",None)}') from None
