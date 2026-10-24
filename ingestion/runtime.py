"""Small shared guards for project commands. Never log connection credentials."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import uuid

DATABASE = 'ecom_source_dev'
ROLES = {'ecom_owner', 'ecom_reader'}


class PipelineError(ValueError):
    """Messages contain only identifiers/counts controlled by project code."""


def connection_settings(expected_user=None):
    if os.environ.get('PGDATABASE') != DATABASE:
        raise PipelineError('PGDATABASE must be ecom_source_dev')
    user = os.environ.get('PGUSER')
    if user not in ROLES or (expected_user and user != expected_user):
        raise PipelineError('Unexpected project role for this command')
    password = Path(os.environ['PG_PASSWORD_FILE']).read_text().strip()
    if len(password) < 16:
        raise PipelineError('A generated project password file is required')
    return dict(host=os.environ['PGHOST'], port=int(os.environ.get('PGPORT', '5432')),
                dbname=DATABASE, user=user, password=password,
                sslmode=os.environ.get('PGSSLMODE', 'prefer'), connect_timeout=10,
                application_name='ecom_pipeline', options='-c statement_timeout=30000')


def guard_pg_identity(conn, expected_user):
    row = conn.execute('''SELECT current_database(), current_user, rolsuper,
        rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
        FROM pg_roles WHERE rolname=current_user''').fetchone()
    if not row or row[:2] != (DATABASE, expected_user) or any(row[2:]):
        raise PipelineError('Unexpected database identity or administrative privileges')
    return row


@contextmanager
def build_lock():
    root = Path(os.environ.get('BUILD_DIR', '/state/build')).resolve()
    if root != Path('/state/build'):
        raise PipelineError('BUILD_DIR must point to the project build volume')
    with (root/'.writer.lock').open('a+') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PipelineError('Another ecom writer holds the build-volume lock') from None
        try:
            yield root
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def json_value(value):
    if isinstance(value, Decimal):
        return '0' if value == 0 else format(value.normalize(), 'f')
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError('Unsupported report value type')


def json_text(value):
    return json.dumps(value, default=json_value, sort_keys=True, ensure_ascii=False)


def write_report(stage, run_id, report):
    root = Path(os.environ.get('ARTIFACT_DIR', '/state/artifacts')).resolve()
    if root != Path('/state/artifacts') or stage not in {'bootstrap', 'extract'}:
        raise PipelineError('Unexpected artifact target')
    folder = root/stage/run_id
    folder.mkdir(parents=True, exist_ok=False)
    pending = folder/'receipt.pending'
    pending.write_text(json_text(report)+'\n', encoding='utf-8')
    pending.replace(folder/'receipt.json')
    return str(folder/'receipt.json')


def run_identity():
    return uuid.uuid4().hex, datetime.now(timezone.utc)
