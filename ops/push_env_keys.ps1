# Copy the two Rakuten keys from the local .env to the VPS .env without printing them.
# The VPS IP is read at run time from C:\Claude\VPS\docs\infra\CONNECTION.md (not stored in this public repo).
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repo '.env'
$conn = 'C:\Claude\VPS\docs\infra\CONNECTION.md'
$key = Join-Path $env:USERPROFILE '.ssh\negura_deploy'

$ip = (Select-String -Path $conn -Pattern 'グローバルIP\s*\|\s*`([0-9.]+)`' -Encoding UTF8).Matches[0].Groups[1].Value
if (-not $ip) { throw 'VPS IP not found in CONNECTION.md' }

$lines = Get-Content -Path $envPath -Encoding UTF8 | Where-Object { $_ -match '^(RAKUTEN_APPLICATION_ID|RAKUTEN_ACCESS_KEY)=' }
if ($lines.Count -ne 2) { throw "expected 2 key lines in .env, found $($lines.Count)" }
foreach ($l in $lines) { $n, $v = $l -split '=', 2; Write-Host ("{0}: length {1}" -f $n, $v.Trim().Length) }

$tmp = [System.IO.Path]::GetTempFileName()
try {
    [System.IO.File]::WriteAllText($tmp, (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding $false))
    & scp -i $key -o BatchMode=yes $tmp "deploy@${ip}:/tmp/kaimono_keys"
    if ($LASTEXITCODE -ne 0) { throw 'scp failed' }
} finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}

$remote = "cd /opt/apps/kaimono && grep -v -e '^RAKUTEN_APPLICATION_ID=' -e '^RAKUTEN_ACCESS_KEY=' .env > .env.new && cat /tmp/kaimono_keys >> .env.new && chmod 600 .env.new && mv .env.new .env && rm -f /tmp/kaimono_keys && grep -c '^RAKUTEN_' .env"
& ssh -i $key -o BatchMode=yes "deploy@$ip" $remote
if ($LASTEXITCODE -ne 0) { throw 'remote update failed' }
Write-Host 'OK: keys written to /opt/apps/kaimono/.env (values not shown). Tell Claude "done".'
