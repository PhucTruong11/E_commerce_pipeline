[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$container = 'airflow-platform-warehouse-laplaptech-1'

function Invoke-SourceSql([string]$Database, [string]$Sql) {
    $result = $Sql | & docker exec -i $container psql -X -q -A -t -v ON_ERROR_STOP=1 -U laplaptech -d $Database 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw 'Provisioning SQL failed. Output suppressed because bootstrap statements can contain secrets. Inspect state before retrying.'
    }
    return ($result -join "`n").Trim()
}

$ownerPath = Join-Path $projectRoot '.local/secrets/owner.password'
$readerPath = Join-Path $projectRoot '.local/secrets/reader.password'
foreach ($path in @($ownerPath, $readerPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw 'Run Initialize-LocalEnv.ps1 first.' }
}
$ownerPassword = [IO.File]::ReadAllText($ownerPath).Trim()
$readerPassword = [IO.File]::ReadAllText($readerPath).Trim()
if ($ownerPassword -notmatch '^[a-f0-9]{64}$' -or $readerPassword -notmatch '^[a-f0-9]{64}$') {
    throw 'Expected locally generated hex secrets. Existing credentials will not be reset.'
}
# Guard the live cluster rather than assuming the container name identifies it.
$identity = Invoke-SourceSql postgres "SELECT current_user || '|' || current_database() || '|' || current_setting('server_version_num')::int / 10000;"
if ($identity -ne 'laplaptech|postgres|16') { throw 'Unexpected shared PostgreSQL admin target.' }
$present = Invoke-SourceSql postgres @'
SELECT (SELECT count(*) FROM pg_database WHERE datname='ecom_source_dev')::text || '|' ||
       (SELECT count(*) FROM pg_roles WHERE rolname IN ('ecom_owner','ecom_reader'))::text;
'@
if ($present -eq '0|0') {
    $null = Invoke-SourceSql postgres @"
BEGIN;
CREATE ROLE ecom_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 4 PASSWORD '$ownerPassword';
CREATE ROLE ecom_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD '$readerPassword';
COMMIT;
"@
    # CREATE DATABASE must be outside a transaction.
    $null = Invoke-SourceSql postgres 'CREATE DATABASE ecom_source_dev OWNER ecom_owner TEMPLATE template0 CONNECTION LIMIT 8;'
    $null = Invoke-SourceSql ecom_source_dev @'
BEGIN;
REVOKE ALL ON DATABASE ecom_source_dev FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE ecom_source_dev TO ecom_owner;
GRANT CONNECT ON DATABASE ecom_source_dev TO ecom_reader;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA e_commerce AUTHORIZATION ecom_owner;
CREATE SCHEMA pipeline_meta AUTHORIZATION ecom_owner;
GRANT USAGE ON SCHEMA e_commerce TO ecom_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE ecom_owner IN SCHEMA e_commerce GRANT SELECT ON TABLES TO ecom_reader;
ALTER ROLE ecom_reader IN DATABASE ecom_source_dev SET default_transaction_read_only TO on;
COMMIT;
'@
    Write-Host 'Created project database, non-superuser roles and empty schemas.'
} elseif ($present -eq '1|2') {
    $ownership = Invoke-SourceSql postgres "SELECT pg_get_userbyid(datdba) || '|' || datconnlimit FROM pg_database WHERE datname='ecom_source_dev';"
    if ($ownership -ne 'ecom_owner|8') { throw 'Existing ecom database differs from the contract; nothing overwritten.' }
    Write-Host 'Existing database/roles preserved; verifying privileges without resetting passwords.'
} else {
    throw 'Partial/existing project provisioning found. Inspect it before retrying; nothing overwritten.'
}
$ownerPassword = $null
$readerPassword = $null

# Real permission probes run in one rolled-back transaction: no source data/table remains.
$verified = Invoke-SourceSql ecom_source_dev @'
BEGIN;
SET LOCAL ROLE ecom_owner;
CREATE TABLE e_commerce.__environment_permission_probe(value integer);
INSERT INTO e_commerce.__environment_permission_probe VALUES (42);
SET LOCAL ROLE ecom_reader;
SELECT CASE WHEN sum(value)=42 THEN 'reader_select_ok' ELSE 'failed' END FROM e_commerce.__environment_permission_probe;
DO $$ BEGIN
  BEGIN
    INSERT INTO e_commerce.__environment_permission_probe VALUES (99);
    RAISE EXCEPTION 'Reader unexpectedly wrote source data';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN
    CREATE TABLE e_commerce.__reader_should_fail(value integer);
    RAISE EXCEPTION 'Reader unexpectedly created a source table';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  IF has_schema_privilege(current_user,'pipeline_meta','USAGE') THEN
    RAISE EXCEPTION 'Reader unexpectedly has metadata access';
  END IF;
END $$;
ROLLBACK;
'@
if ($verified -ne 'reader_select_ok') { throw 'Permission probe did not produce the expected result.' }
Write-Host 'PASS: reader SELECT; reader INSERT/CREATE denied; metadata private; probe rolled back.'
Write-Host 'Next: run Invoke-Dev.ps1 checks using each real login over TCP.'
