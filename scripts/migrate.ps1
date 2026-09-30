param(
    [string]$DbName = "",
    [switch]$Test
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
$sqlFile = Join-Path $PSScriptRoot "init_db.sql"

if (-not (Test-Path $envFile)) { throw "Cannot find $envFile" }
if (-not (Test-Path $sqlFile)) { throw "Cannot find $sqlFile" }

Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    $name, $value = $line -split "=", 2
    if (-not $name) { return }
    Set-Item -Path ("Env:" + $name.Trim()) -Value $value.Trim().Trim('"').Trim("'")
}

if ([string]::IsNullOrWhiteSpace($env:MYSQL_USER) -or
    [string]::IsNullOrWhiteSpace($env:MYSQL_PASSWORD) -or
    [string]::IsNullOrWhiteSpace($env:MYSQL_DATABASE)) {
    throw ".env missing MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE"
}

Set-Location $root

function Assert-ExitCode {
    param([string]$Action)
    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed, exit code=$LASTEXITCODE"
    }
}

function Invoke-MysqlSql {
    param(
        [Parameter(Mandatory = $true)][string]$User,
        [Parameter(Mandatory = $true)][string]$Password,
        [Parameter(Mandatory = $true)][string]$Sql,
        [string]$Database = ""
    )

    $mysqlArgs = @(
        "exec", "-T", "mysql", "mysql",
        "--user=$User",
        "--password=$Password",
        "--host=127.0.0.1",
        "--default-character-set=utf8mb4"
    )
    if (-not [string]::IsNullOrWhiteSpace($Database)) {
        $mysqlArgs += $Database
    }

    $Sql | docker compose @mysqlArgs
    Assert-ExitCode "mysql as $User"
}

if ($Test) {
    if ([string]::IsNullOrWhiteSpace($env:MYSQL_TEST_DATABASE)) {
        throw ".env missing MYSQL_TEST_DATABASE"
    }
    if ([string]::IsNullOrWhiteSpace($env:MYSQL_ROOT_PASSWORD)) {
        throw ".env missing MYSQL_ROOT_PASSWORD"
    }

    $targetDb = $env:MYSQL_TEST_DATABASE
    $setupSql = @"
CREATE DATABASE IF NOT EXISTS ``$targetDb`` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL ON ``$targetDb``.* TO '$($env:MYSQL_USER)'@'%';
FLUSH PRIVILEGES;
"@

    Invoke-MysqlSql -User "root" -Password $env:MYSQL_ROOT_PASSWORD -Sql $setupSql
}
else {
    $targetDb = if ([string]::IsNullOrWhiteSpace($DbName)) { $env:MYSQL_DATABASE } else { $DbName }
}

$initSql = Get-Content -Raw $sqlFile
Invoke-MysqlSql -User $env:MYSQL_USER -Password $env:MYSQL_PASSWORD -Sql $initSql -Database $targetDb

Write-Host "migrated: $targetDb"