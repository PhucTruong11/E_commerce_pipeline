"""Project CLI: environment checks, one-time bootstrap and snapshot extraction."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import duckdb
import psycopg

from ingestion.runtime import (PipelineError, build_lock, connection_settings,
                               guard_pg_identity, json_text)


def check_postgres():
    with psycopg.connect(**connection_settings()) as conn:
        identity = guard_pg_identity(conn, os.environ['PGUSER'])
        source_create, meta_usage = conn.execute("""
            SELECT has_schema_privilege(current_user,'e_commerce','CREATE'),
                   has_schema_privilege(current_user,'pipeline_meta','USAGE')
        """).fetchone()
        owner = identity[1] == 'ecom_owner'
        if (source_create, meta_usage) != (owner, owner):
            raise PipelineError('Source/meta schema privileges differ from project contract')
        count = conn.execute("""SELECT count(*) FROM information_schema.tables
                                WHERE table_schema='e_commerce'""").fetchone()[0]
    return dict(database=identity[0], user=identity[1], admin=False, source_tables=count,
                source_create=source_create, metadata_usage=meta_usage)


def smoke_duckdb(path):
    with duckdb.connect(str(path), config={'memory_limit': '512MB', 'threads': 1}) as conn:
        conn.execute('CREATE TABLE environment_probe(value INTEGER)')
        conn.execute('INSERT INTO environment_probe VALUES (42)')
        if conn.execute('SELECT sum(value) FROM environment_probe').fetchone() != (42,):
            raise PipelineError('DuckDB round-trip failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'dbt-debug', 'versions', 'bootstrap', 'extract'], default='check', nargs='?')
    args = parser.parse_args()
    if args.command in {'bootstrap', 'extract'}:
        if args.command == 'bootstrap':
            from scripts.bootstrap.load_csv import bootstrap
            result = bootstrap()
        else:
            from ingestion.loaders.postgres_to_duckdb import extract
            result = extract()
        print(json_text(result))
        return
    packages = {p: version(p) for p in ['dbt-core', 'dbt-duckdb', 'duckdb', 'psycopg']}
    if args.command == 'versions':
        print(json.dumps({'python': sys.version.split()[0], **packages}, indent=2))
        return
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'packages': packages,
              'postgres': check_postgres(), 'uid': os.getuid()}
    with build_lock() as build:
        run_id = 'environment-' + uuid.uuid4().hex
        candidate = build / (run_id + '.duckdb')
        try:
            smoke_duckdb(candidate)
            report['duckdb'] = 'round_trip_passed'
            report['input_files_present'] = all((Path('/input') / name).is_file() for name in
                ['customer.csv', 'ecom_sales.csv', 'product.csv', 'region.csv'])
            for target in ['/state/releases', '/state/artifacts']:
                probe = Path(target) / (run_id + '.tmp')
                probe.write_text('environment check')
                probe.unlink()
            if args.command == 'dbt-debug':
                artifact = Path('/state/artifacts') / run_id
                env = {**os.environ, 'ECOM_DUCKDB_PATH': str(candidate),
                       'DBT_TARGET_PATH': str(artifact / 'target')}
                result = subprocess.run(['dbt', 'debug', '--project-dir', '/app/dbt',
                    '--profiles-dir', '/app/config', '--target', 'dev',
                    '--log-path', str(artifact / 'logs')],
                    env=env, check=False)
                if result.returncode:
                    raise PipelineError('dbt debug failed; see its DuckDB-only output')
                report['dbt_debug'] = 'passed'
            report['cgroup'] = {name: Path('/sys/fs/cgroup', name).read_text().strip()
                                for name in ['memory.max', 'cpu.max', 'pids.max']}
            report['status'] = 'success'
            (Path('/state/artifacts') / 'environment-latest.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
        finally:
            candidate.unlink(missing_ok=True)
            Path(str(candidate) + '.wal').unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except psycopg.Error as error:
        # Driver messages may include connection details; expose only type/SQLSTATE.
        print(json.dumps({'status': 'failed', 'error': type(error).__name__, 'sqlstate': error.sqlstate}), file=sys.stderr)
        raise SystemExit(1) from None
    except PipelineError as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error': type(error).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
