#!/usr/bin/env pwsh
# Repo-Helfer: .env in die aktuelle Sitzung laden, dann `tessera` mit den
# uebergebenen Argumenten ausfuehren. So muss die Import-DotEnv-Logik NICHT ins
# persoenliche $PROFILE - sie lebt eingecheckt im Repo, eine Stelle fuer alle.
#
#   ./scripts/tessera.ps1 preflight
#   ./scripts/tessera.ps1 run --id hund-anmelden
#
# tessera liest Keys ausschliesslich aus dem Prozess-ENV (os.environ) und laedt
# .env nie selbst; dieses Skript schliesst genau diese Luecke. Es schreibt keine
# Keys in Logs und gibt keine Werte aus.
#
# Liegt im Repo eine .venv, nimmt das Skript `tessera` direkt von dort - die
# Umgebung muss also nicht aktiviert sein (sonst: CommandNotFoundException in
# jedem neuen Fenster). Ohne .venv gilt `tessera` aus dem PATH.
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'

# .env relativ zur Repo-Wurzel (ein Verzeichnis ueber scripts/), unabhaengig vom CWD.
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot '.env'

if (Test-Path $envPath) {
    Get-Content $envPath | Where-Object { $_ -match '^\s*[^#].+=' } | ForEach-Object {
        $name, $value = $_ -split '=', 2
        Set-Item -Path "Env:$($name.Trim())" -Value $value.Trim().Trim('"')
    }
} else {
    Write-Warning "$envPath nicht gefunden - fahre ohne .env fort (ENV evtl. anderweitig gesetzt)."
}

# tessera aus der Repo-.venv (Windows: Scripts\tessera.exe, sonst bin/tessera),
# sonst aus dem PATH.
$tessera = 'tessera'
foreach ($candidate in @(
        (Join-Path $repoRoot '.venv\Scripts\tessera.exe'),
        (Join-Path $repoRoot '.venv/bin/tessera'))) {
    if (Test-Path $candidate) {
        $tessera = $candidate
        break
    }
}

& $tessera @Rest
exit $LASTEXITCODE
