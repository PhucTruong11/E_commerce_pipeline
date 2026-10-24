"""One-time CSV bootstrap. All four sources and the ledger commit together."""
import os
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from ingestion.runtime import (PipelineError, build_lock, connection_settings,
    guard_pg_identity, run_identity, write_report)
from ingestion.sources.csv_contracts import CONTRACTS
from ingestion.sources.table_contracts import (ORDER, VERSION, TableStats, columns,
    load_input, schema_signature, validate_source_schema)


def create_source_tables(pg):
    for table in ORDER:
        fields = [sql.SQL('{} {} {}').format(sql.Identifier(name), sql.SQL(kind),
                  sql.SQL('NOT NULL' if required else '')) for name,kind,required in columns(table)]
        fields.append(sql.SQL('PRIMARY KEY ({})').format(sql.Identifier(CONTRACTS[table][0])))
        pg.execute(sql.SQL('CREATE TABLE {} ({})').format(sql.Identifier('e_commerce',table), sql.SQL(',').join(fields)))
    pg.execute('''CREATE TABLE pipeline_meta.bootstrap_runs (
        singleton smallint PRIMARY KEY CHECK(singleton=1), bootstrap_id text NOT NULL,
        contract_version text NOT NULL, schema_signature text NOT NULL,
        files jsonb NOT NULL, loaded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP)''')


def copy_table(pg, table, rows):
    statement = sql.SQL('COPY {} ({}) FROM STDIN').format(sql.Identifier('e_commerce',table),
        sql.SQL(',').join(map(sql.Identifier, CONTRACTS[table][1])))
    with pg.cursor() as cur, cur.copy(statement) as stream:
        for row in rows:
            stream.write_row(row)


def source_stats(pg, table):
    query = sql.SQL('SELECT {} FROM {} ORDER BY {} COLLATE "C"').format(
        sql.SQL(',').join(map(sql.Identifier, CONTRACTS[table][1])),
        sql.Identifier('e_commerce',table), sql.Identifier(CONTRACTS[table][0]))
    stats = TableStats(table)
    with pg.cursor(name=f'validate_{table}') as cur:
        cur.execute(query)
        while rows := cur.fetchmany(1000):
            stats.add(rows)
    return stats.report()


def bootstrap():
    settings = connection_settings('ecom_owner')
    with build_lock():
        run_id, started_at = run_identity()
        datasets, files, orphan, fingerprint = load_input(Path(os.environ.get('INPUT_DIR','/input')))
        status, statistics = 'loaded', {}
        with psycopg.connect(**settings, autocommit=True) as pg, pg.transaction():
            guard_pg_identity(pg, 'ecom_owner')
            pg.execute('SELECT pg_advisory_xact_lock(640101, 1)')
            ledger_exists = pg.execute("SELECT to_regclass('pipeline_meta.bootstrap_runs') IS NOT NULL").fetchone()[0]
            if ledger_exists:
                validate_source_schema(pg)
                previous = pg.execute('SELECT bootstrap_id,contract_version,schema_signature,files FROM pipeline_meta.bootstrap_runs WHERE singleton=1').fetchone()
                if not previous or previous != (fingerprint, VERSION, schema_signature(), files):
                    raise PipelineError('Different or incomplete baseline: source was preserved; explicit new-baseline workflow required')
                status = 'skipped'
            else:
                occupied = pg.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='e_commerce'").fetchone()[0]
                if occupied:
                    raise PipelineError('Source tables exist without the project ledger; nothing overwritten')
                create_source_tables(pg)
                for table in ORDER:
                    copy_table(pg, table, datasets[table])
                for table in ORDER:
                    expected = TableStats(table)
                    key_position = CONTRACTS[table][1].index(CONTRACTS[table][0])
                    expected.add(sorted(datasets[table], key=lambda row:row[key_position].encode('utf-8')))
                    statistics[table] = source_stats(pg, table)
                    if statistics[table] != expected.report():
                        raise PipelineError(f'Bootstrap reconciliation failed: table={table}')
                pg.execute('''INSERT INTO pipeline_meta.bootstrap_runs
                    (singleton,bootstrap_id,contract_version,schema_signature,files)
                    VALUES (1,%s,%s,%s,%s)''', (fingerprint,VERSION,schema_signature(),Jsonb(files)))
        report = {'status':status, 'run_id':run_id, 'bootstrap_id':fingerprint,
            'contract_version':VERSION, 'started_at':started_at, 'baseline_files':files,
            'orphan_counts':orphan, 'orphan_policy':'preserve_and_report', 'tables':statistics}
        report['receipt'] = write_report('bootstrap',run_id,report)
        return report
