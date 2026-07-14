# CACP one-line installer (Windows PowerShell).
#
#   irm https://raw.githubusercontent.com/renf0x/ctx-agent-context-stack/main/install.ps1 | iex
#
# Downloads the single self-contained ctx.py into the current project and runs
# `python ctx.py init` to scaffold the memory vault, agent adapters, and a first
# cache-stable startup packet. Non-destructive: existing files are kept.
#
# Target dir / agents can be overridden before piping to iex:
#   $env:CACP_TARGET = "C:\path\to\project"; $env:CACP_AGENTS = "generic,claude"
[CmdletBinding()]
param(
    [string]$Target = $(if ($env:CACP_TARGET) { $env:CACP_TARGET } else { "." }),
    [string]$Agents = $(if ($env:CACP_AGENTS) { $env:CACP_AGENTS } else { "all" })
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$raw = "https://raw.githubusercontent.com/renf0x/ctx-agent-context-stack/main/ctx.py"

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { Write-Error "Python 3.10+ is required but was not found on PATH."; exit 1 }

if (-not (Test-Path $Target)) { New-Item -ItemType Directory -Force -Path $Target | Out-Null }
$dest = Join-Path $Target "ctx.py"
Write-Host "Downloading ctx.py -> $dest"
Invoke-WebRequest -Uri $raw -OutFile $dest -UseBasicParsing

Write-Host "Scaffolding CACP (agents: $Agents)"
Push-Location $Target
try { & $py ctx.py init --agents $Agents } finally { Pop-Location }

Write-Host ""
Write-Host "Done. Open the project with your coding agent; it will read"
Write-Host ".ctx/startup-packet.md. Check real savings any time: python ctx.py measure"
