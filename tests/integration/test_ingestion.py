"""Run with host Python stdlib + Docker; all data/PG objects are disposable fixtures."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


def child_checks():
    sys.path.insert(0, '/app')
    import csv
    from decimal import Decimal
    from unittest.mock import patch
    import duckdb
    import psycopg
    from ingestion.runtime import PipelineError, build_lock, connection_settings
    from ingestion.sources.csv_contracts import CONTRACTS
    from ingestion.sources.table_contracts import convert
    from scripts.bootstrap import load_csv
    from ingestion.loaders import postgres_to_duckdb as loader

    assert os.environ['PGHOST'].startswith('ecom-test-'), 'Fixture tests refuse the real warehouse'
    work=Path('/tmp/ingestion-fixture'); work.mkdir()
    owner=work/'owner.password'; owner.write_text('synthetic-owner-password')
    reader=work/'reader.password'; reader.write_text('synthetic-reader-password')
    os.environ.update(INPUT_DIR=str(work),PGUSER='ecom_owner',PG_PASSWORD_FILE=str(owner))
    rows={
      'customer':[['C1','Alice','Synthetic','1990-01-01','M','F','alice@example.test','1000','School','Test','Y'],
                  ['C2','Bob','Synthetic','1991-01-01','S','NULL','bob@example.test','2000','School','Test','N']],
      'product':[['P1','Test product','Test category','Test subcategory']],
      'region':[['R1','Test city','Test state','Test country','10.123456','100.123456','Test region','Test market']],
      'ecom_sales':[['S1','O1','2024-01-01','C1','Test','R1','P1','1','20.00','0.10','2.00'],
                    ['S2','O2','2024-01-02','C2','Test','UNKNOWN','UNKNOWN','2','11.50','0.20','-1.00']],
    }
    for table,items in rows.items():
        with (work/f'{table}.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream); writer.writerow(CONTRACTS[table][1]); writer.writerows(items)
    def owner_sql(query,args=()):
        with patch.dict(os.environ,PGUSER='ecom_owner',PG_PASSWORD_FILE=str(owner)):
            with psycopg.connect(**connection_settings('ecom_owner'),autocommit=True) as pg:
                return pg.execute(query,args).fetchall() if query.lstrip().upper().startswith('SELECT') else pg.execute(query,args)
    checks={}
    with build_lock():
        try:
            with build_lock():
                raise AssertionError('Second writer acquired the lock')
        except PipelineError:
            pass
    with build_lock():
        pass
    checks['writer_lock_and_release']='passed'
    original=load_csv.copy_table
    def fail_last(pg,table,items):
        if table=='ecom_sales': raise RuntimeError('synthetic failure')
        return original(pg,table,items)
    with patch.object(load_csv,'copy_table',side_effect=fail_last):
        try: load_csv.bootstrap()
        except RuntimeError: pass
        else: raise AssertionError('Injected COPY-stage failure was accepted')
    assert owner_sql("SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('e_commerce','pipeline_meta')")==[(0,)]
    checks['atomic_rollback']='passed'
    initial=load_csv.bootstrap()
    assert initial['status']=='loaded' and initial['orphan_counts']['product_code']==1
    assert load_csv.bootstrap()['status']=='skipped'
    checks['bootstrap_and_identical_retry']='passed'
    path=work/'customer.csv'; saved=path.read_bytes(); path.write_bytes(saved.replace(b'Alice',b'Changed'))
    try: load_csv.bootstrap()
    except PipelineError: pass
    else: raise AssertionError('Changed baseline was not rejected')
    path.write_bytes(saved)
    assert owner_sql("SELECT first_name FROM e_commerce.customer WHERE customer_id='C1'")==[('Alice',)]
    checks['changed_input_preserves_source']='passed'
    for raw in ['1.001','NaN','Infinity']:
        try: convert(raw,'numeric(20,2)',False)
        except ValueError: pass
        else: raise AssertionError('Lossy/non-finite numeric accepted')
    checks['decimal_precision']='passed'
    with patch.dict(os.environ,PGUSER='ecom_reader',PG_PASSWORD_FILE=str(reader)):
        with psycopg.connect(**connection_settings('ecom_reader'),autocommit=True) as pg:
            for statement in ["INSERT INTO e_commerce.product VALUES ('P2','x','x','x')", 'SELECT * FROM pipeline_meta.bootstrap_runs']:
                try: pg.execute(statement)
                except (psycopg.errors.InsufficientPrivilege,psycopg.errors.ReadOnlySqlTransaction): pass
                else: raise AssertionError('Reader unexpectedly accessed protected operation')
        checks['reader_permissions']='passed'
        before=set(Path('/state/build').rglob('*.duckdb'))
        original_write=loader.write_batch
        def fail_mid(duck,table,batch,extraction_id,stamp):
            if table=='region': raise RuntimeError('synthetic extraction failure')
            return original_write(duck,table,batch,extraction_id,stamp)
        with patch.object(loader,'write_batch',side_effect=fail_mid):
            try: loader.extract()
            except PipelineError: pass
            else: raise AssertionError('Failed extract marked successful')
        assert set(Path('/state/build').rglob('*.duckdb'))==before
        checks['partial_candidate_cleanup']='passed'
        changed=False
        def update_source(duck,table,batch,extraction_id,stamp):
            nonlocal changed
            original_write(duck,table,batch,extraction_id,stamp)
            if table=='customer' and not changed:
                owner_sql("UPDATE e_commerce.ecom_sales SET profit=99 WHERE row_id='S1'")
                changed=True
        with patch.object(loader,'write_batch',side_effect=update_source):
            snapshot=loader.extract()
        assert snapshot['tables']['ecom_sales']['sums']['profit']==Decimal('1.00')
        assert snapshot['tables']['ecom_sales']['rows']==2
        with duckdb.connect(snapshot['candidate'],read_only=True) as duck:
            assert duck.execute('SELECT count(*) FROM bronze.ecom_sales').fetchone()==(2,)
        fresh=loader.extract()
        assert fresh['tables']['ecom_sales']['sums']['profit']==Decimal('98.00')
        assert fresh['candidate']!=snapshot['candidate']
        checks['consistent_snapshot_and_new_candidate']='passed'
        try: load_csv.bootstrap()
        except PipelineError: pass
        else: raise AssertionError('Reader bootstrap was not rejected')
    assert load_csv.bootstrap()['status']=='skipped'
    assert owner_sql("SELECT profit FROM e_commerce.ecom_sales WHERE row_id='S1'")==[(Decimal('99.00'),)]
    checks['retry_preserves_oltp_changes']='passed'
    with patch.dict(os.environ,PGDATABASE='postgres'):
        try: load_csv.bootstrap()
        except PipelineError: pass
        else: raise AssertionError('Wrong database accepted')
    checks['identity_guards']='passed'
    print(json.dumps({'status':'success','checks':checks,'data':'synthetic only'},indent=2))


def host_checks():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform-dir',type=Path,required=True)
    args=parser.parse_args()
    policy=json.loads((args.platform_dir/'resources.json').read_text(encoding='utf-8-sig'))
    def docker(*values,input=None,timeout=60):
        result=subprocess.run(['docker',*values],input=input,text=True,capture_output=True,timeout=timeout)
        if result.returncode: raise RuntimeError(result.stderr.strip() or 'Docker operation failed')
        return result.stdout.strip()
    ids=docker('ps','-q').splitlines()
    live=json.loads(docker('inspect',*ids)) if ids else []
    memory=0
    for item in live:
        labels=item['Config'].get('Labels') or {}
        if labels.get('com.docker.compose.service')=='airflow-scheduler':
            raise RuntimeError('Fixture tests require the shared scheduler OFF')
        if not item['HostConfig']['Memory']: raise RuntimeError('Running container has no memory cap')
        memory+=item['HostConfig']['Memory']/1024**2
    needed=memory+384+1024+policy['headroom_mib']+policy['host']['engine_overhead_mib']
    engine=json.loads(docker('info','--format','{{json .}}'))
    if needed>policy['host']['memory_mib'] or needed-policy['host']['engine_overhead_mib']>engine['MemTotal']/1024**2:
        raise RuntimeError('Insufficient budget for isolated fixture PostgreSQL + runtime')
    name='ecom-test-'+uuid.uuid4().hex[:10]
    network_created=container_created=False
    try:
        docker('network','create',name); network_created=True
        docker('run','-d','--name',name+'-pg','--network',name,'--memory','384m','--memory-swap','384m',
            '--cpus','.5','--pids-limit','128','--tmpfs','/var/lib/postgresql/data:size=134217728',
            '-e','POSTGRES_USER=fixture_admin','-e','POSTGRES_HOST_AUTH_METHOD=trust',
            'postgres:16','-c','shared_buffers=32MB','-c','max_connections=20')
        container_created=True
        for attempt in range(40):
            try:
                docker('exec',name+'-pg','pg_isready','-h','127.0.0.1','-U','fixture_admin','-d','postgres'); break
            except RuntimeError:
                time.sleep(.5)
        else: raise RuntimeError('Fixture PostgreSQL did not start')
        docker('exec',name+'-pg','psql','-X','-U','fixture_admin','-d','postgres','-v','ON_ERROR_STOP=1','-c',
               'CREATE ROLE ecom_owner LOGIN; CREATE ROLE ecom_reader LOGIN;')
        docker('exec',name+'-pg','createdb','-U','fixture_admin','-O','ecom_owner','ecom_source_dev')
        docker('exec',name+'-pg','psql','-X','-U','fixture_admin','-d','ecom_source_dev','-v','ON_ERROR_STOP=1','-c',
            '''REVOKE ALL ON DATABASE ecom_source_dev FROM PUBLIC;
            GRANT CONNECT ON DATABASE ecom_source_dev TO ecom_owner,ecom_reader;
            CREATE SCHEMA e_commerce AUTHORIZATION ecom_owner;
            CREATE SCHEMA pipeline_meta AUTHORIZATION ecom_owner;
            GRANT USAGE ON SCHEMA e_commerce TO ecom_reader;
            ALTER DEFAULT PRIVILEGES FOR ROLE ecom_owner IN SCHEMA e_commerce GRANT SELECT ON TABLES TO ecom_reader;
            ALTER ROLE ecom_reader IN DATABASE ecom_source_dev SET default_transaction_read_only TO on;''')
        output=docker('run','--rm','--network',name,'--memory','1024m','--memory-swap','1024m','--cpus','1',
            '--pids-limit','256','--read-only','--tmpfs','/tmp:size=134217728,mode=1777',
            '--tmpfs','/state/build:size=268435456,uid=10001,gid=10001,mode=0770',
            '--tmpfs','/state/artifacts:size=67108864,uid=10001,gid=10001,mode=0770',
            '--mount',f'type=bind,source={Path(__file__).resolve()},target=/test_ingestion.py,readonly',
            '-e','ECOM_FIXTURE_CHILD=1','-e',f'PGHOST={name}-pg','-e','PGDATABASE=ecom_source_dev','-e','PGSSLMODE=disable',
            '--entrypoint','python','ecom-runtime:local-v1','/test_ingestion.py',timeout=180)
        print(output)
    finally:
        if container_created: docker('rm','-f',name+'-pg')
        if network_created: docker('network','rm',name)


if __name__=='__main__':
    if os.environ.get('ECOM_FIXTURE_CHILD')=='1': child_checks()
    else: host_checks()
