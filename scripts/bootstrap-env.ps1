$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot '.env'

if (Test-Path -LiteralPath $envPath) {
    Write-Host '.env already exists; leaving it unchanged.'
    exit 0
}

function New-Secret([int]$Bytes = 32) {
    $buffer = [byte[]]::new($Bytes)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    return [BitConverter]::ToString($buffer).Replace("-", "").ToLowerInvariant()
}

function New-Base32Secret([int]$Length = 32) {
    $alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
    $buffer = [byte[]]::new($Length)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    $chars = foreach ($byte in $buffer) { $alphabet[[int]($byte -band 31)] }
    return -join $chars
}

$lines = @(
    'PORTFLOW_APP_ENV=development',
    'PORTFLOW_DEMO_MODE=true',
    ('PORTFLOW_JWT_SECRET=' + (New-Secret 48)),
    ('POSTGRES_ADMIN_PASSWORD=' + (New-Secret 32)),
    ('PORTFLOW_DB_PASSWORD=' + (New-Secret 32)),
    'PORTFLOW_DATABASE_URL=postgresql+psycopg://portflow_app:replace-me@db:5432/portflow',
    'PORTFLOW_REDIS_URL=redis://redis:6379/0',
    'PORTFLOW_CORS_ORIGINS=http://localhost:5173,http://localhost:8080',
    'PORTFLOW_ACCESS_TOKEN_MINUTES=30',
    ('PORTFLOW_DEMO_ADMIN_PASSWORD=' + (New-Secret 24)),
    ('PORTFLOW_DEMO_CUSTOMER_PASSWORD=' + (New-Secret 24)),
    ('PORTFLOW_DEMO_ADMIN_MFA_SECRET=' + (New-Base32Secret 32)),
    'PORTFLOW_DEMO_ADMIN_EMAIL=admin@demo.portflow.local',
    'PORTFLOW_DEMO_CUSTOMER_EMAIL=customer@demo.portflow.local'
)
$dbPassword = ($lines | Where-Object { $_ -like 'PORTFLOW_DB_PASSWORD=*' }) -replace '^PORTFLOW_DB_PASSWORD=', ''
$lines = $lines | ForEach-Object {
    if ($_ -like 'PORTFLOW_DATABASE_URL=*') {
        'PORTFLOW_DATABASE_URL=postgresql+psycopg://portflow_app:' + $dbPassword + '@db:5432/portflow'
    } else { $_ }
}
Set-Content -LiteralPath $envPath -Value $lines -Encoding UTF8
Write-Host 'Created .env with fresh local-only secrets. Values were not displayed.'


