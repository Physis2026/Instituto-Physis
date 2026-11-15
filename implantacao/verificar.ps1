# Saude da instalacao Windows (equivalente ao verificar.sh). ASCII de proposito (PowerShell 5.1).
[CmdletBinding()]
param([int]$MaxHorasBackup = 26)
$ErrorActionPreference = "Continue"
$Base = Join-Path $env:ProgramData "Physis"
$falhas = 0
function Ok($t) { Write-Host "  [ OK  ] $t" }
function Aviso($t) { Write-Host "  [AVISO] $t" -ForegroundColor Yellow }
function Ruim($t) { Write-Host "  [FALHA] $t" -ForegroundColor Red; $script:falhas++ }

$porta = 8700
if (Test-Path "$Base\physis.env") {
    $l = Get-Content "$Base\physis.env" | Where-Object { $_ -match '^PHYSIS_PORTA=' } | Select-Object -Last 1
    if ($l) { $porta = [int]($l -split '=', 2)[1] }
}
Write-Host "Physis Hub - verificacao ($env:COMPUTERNAME $(Get-Date -Format 'dd/MM/yyyy HH:mm'))"

$svc = Get-Service PhysisHub -ErrorAction SilentlyContinue
$tar = Get-ScheduledTask -TaskName PhysisHub -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") { Ok "servico PhysisHub rodando" }
elseif ($tar -and $tar.State -eq "Running") { Ok "tarefa PhysisHub rodando" }
else { Ruim "PhysisHub parado (veja $Base\logs\physis-hub.log)" }

try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://127.0.0.1:$porta/api/saude"
    $s = $r.Content | ConvertFrom-Json
    Ok "porta $porta respondendo"
    if ($s.registro.integro) { Ok "cadeia do registro integra ($($s.registro.entradas) entradas)" }
    else { Ruim "cadeia do registro QUEBRADA - nao apague nada; avise a Physis" }
} catch {
    $cod = $null
    if ($_.Exception.Response) { $cod = [int]$_.Exception.Response.StatusCode }
    if ($cod -eq 401 -or $cod -eq 403) { Ok "porta $porta respondendo"; Aviso "/api/saude pede sessao (instalacao exposta)" }
    else { Ruim "porta $porta / api/saude: $($_.Exception.Message)" }
}

$letra = (Split-Path -Qualifier $Base).TrimEnd(':')
$d = Get-PSDrive $letra
$uso = [math]::Round(100 * $d.Used / ($d.Used + $d.Free))
if ($uso -ge 95) { Ruim "disco $uso% cheio" } elseif ($uso -ge 85) { Aviso "disco $uso% cheio" } else { Ok "disco $uso% usado" }

$marca = Join-Path $Base "backups\ultimo.json"
if (Test-Path $marca) {
    $q = (Get-Content $marca | ConvertFrom-Json).quando
    $h = [math]::Floor(([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $q) / 3600)
    if ($h -gt $MaxHorasBackup) { Ruim "ultima copia de seguranca ha $h h" } else { Ok "ultima copia de seguranca ha $h h" }
} elseif (Test-Path "$Base\backup.env") { Ruim "copia configurada mas nunca feita" }
else { Aviso "copia de seguranca nao configurada ($Base\backup.env)" }

if ($falhas -gt 0) { Write-Host "Resultado: $falhas falha(s)."; exit 1 }
Write-Host "Resultado: tudo certo."
