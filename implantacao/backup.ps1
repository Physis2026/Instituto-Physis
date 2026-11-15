# Copia de seguranca do Physis Hub no Windows (equivalente ao backup.sh). ASCII de proposito (PowerShell 5.1).
# Le %ProgramData%\Physis\backup.env (mesmas chaves do backup.env.exemplo: DESTINO, CIFRA, AGE_DESTINATARIO,
# OPENSSL_SENHA_ARQUIVO, MANTER_DIARIAS/SEMANAIS/MENSAIS). Cifra com age.exe (recomendado) ou openssl.exe.
#
#   powershell -ExecutionPolicy Bypass -File backup.ps1 [-Rotulo pre-atualizacao]
[CmdletBinding()]
param([string]$Rotulo = "", [string]$Config = "")
$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3

$Base = Join-Path $env:ProgramData "Physis"
if (-not $Config) { $Config = Join-Path $Base "backup.env" }
function Falha($t) { Write-Host "backup FALHOU: $t" -ForegroundColor Red; exit 1 }
function LerEnv($arq) {
    $h = @{}
    if (Test-Path $arq) {
        Get-Content $arq | Where-Object { $_ -match '^[A-Z_][A-Z0-9_]*=' } | ForEach-Object { $k, $v = $_ -split '=', 2; $h[$k] = $v }
    }
    return $h
}
if (-not (Test-Path $Config)) { Falha "sem $Config" }
if ($Rotulo -notmatch '^[a-z0-9-]*$') { Falha "rotulo invalido" }
$c = LerEnv $Config
$hub = LerEnv (Join-Path $Base "physis.env")
$banco = $(if ($hub["PHYSIS_BANCO"]) { $hub["PHYSIS_BANCO"] } else { Join-Path $Base "dados\physis-hub.db" })
$destino = $c["DESTINO"]; if (-not $destino) { Falha "DESTINO vazio" }
if (-not (Test-Path $destino)) { Falha "$destino nao existe (pendrive ausente?)" }
$cifra = $(if ($c["CIFRA"]) { $c["CIFRA"] } else { "age" })
$py = (Get-Content "C:\Physis\iniciar-hub.ps1" | Select-String "-m physis_hub" | ForEach-Object { ($_.Line -split "'")[1] } | Select-Object -First 1)
if (-not $py) { $py = "python" }

$tmp = Join-Path $env:TEMP ("physis-bkp-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $nome = "physis-$env:COMPUTERNAME-" + (Get-Date -Format "yyyyMMdd-HHmmss") + $(if ($Rotulo) { "-$Rotulo" } else { "" })
    $pasta = Join-Path $tmp $nome
    New-Item -ItemType Directory -Path $pasta | Out-Null
    $copia = Join-Path $pasta "physis-hub.db"
    $codigo = "import sqlite3,sys`ns=sqlite3.connect(sys.argv[1],timeout=30);d=sqlite3.connect(sys.argv[2])`nwith d: s.backup(d)`nr=d.execute('PRAGMA integrity_check').fetchone()[0];d.execute('PRAGMA journal_mode=DELETE');d.close();s.close()`nsys.exit(0 if r=='ok' else 'integrity_check: '+r)"
    & $py -c $codigo $banco $copia
    if ($LASTEXITCODE -ne 0) { Falha "copia do banco" }
    if (Test-Path "C:\Physis\atual\instancia.json") { Copy-Item "C:\Physis\atual\instancia.json" $pasta }
    $zip = "$pasta.zip"
    Compress-Archive -Path $pasta -DestinationPath $zip
    if ($cifra -eq "age") {
        $age = Get-Command age -ErrorAction SilentlyContinue
        if (-not $age) { Falha "age.exe nao encontrado no PATH" }
        if ($c["AGE_DESTINATARIO"] -notlike "age1*") { Falha "AGE_DESTINATARIO vazio" }
        $saida = "$nome.zip.age"
        & $age.Source -r $c["AGE_DESTINATARIO"] -o (Join-Path $tmp $saida) $zip
    } elseif ($cifra -eq "openssl") {
        $ossl = Get-Command openssl -ErrorAction SilentlyContinue
        if (-not $ossl) { Falha "openssl.exe nao encontrado no PATH" }
        $saida = "$nome.zip.enc"
        & $ossl.Source enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass ("file:" + $c["OPENSSL_SENHA_ARQUIVO"]) -in $zip -out (Join-Path $tmp $saida)
    } else { Falha "CIFRA deve ser age ou openssl" }
    if ($LASTEXITCODE -ne 0) { Falha "cifra" }

    $sub = $(if ($Rotulo) { "avulsas" } else { "diarias" })
    foreach ($p in @("diarias", "semanais", "mensais", "avulsas")) { New-Item -ItemType Directory -Force -Path (Join-Path $destino $p) | Out-Null }
    Copy-Item (Join-Path $tmp $saida) (Join-Path $destino $sub)
    if (-not $Rotulo) {
        if ((Get-Date).DayOfWeek -eq "Sunday") { Copy-Item (Join-Path $tmp $saida) (Join-Path $destino "semanais") }
        if ((Get-Date).Day -eq 1) { Copy-Item (Join-Path $tmp $saida) (Join-Path $destino "mensais") }
    }
    $manter = @{ "diarias" = [int]$(if ($c["MANTER_DIARIAS"]) { $c["MANTER_DIARIAS"] } else { 7 });
                 "semanais" = [int]$(if ($c["MANTER_SEMANAIS"]) { $c["MANTER_SEMANAIS"] } else { 4 });
                 "mensais" = [int]$(if ($c["MANTER_MENSAIS"]) { $c["MANTER_MENSAIS"] } else { 12 }); "avulsas" = 5 }
    foreach ($p in $manter.Keys) {
        Get-ChildItem (Join-Path $destino $p) -Filter "physis-*" | Sort-Object LastWriteTime -Descending |
            Select-Object -Skip $manter[$p] | Remove-Item -Force
    }
    $marca = @{ quando = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds(); arquivo = $saida; destino = (Join-Path $destino $sub) } | ConvertTo-Json -Compress
    Set-Content -Path (Join-Path $Base "backups\ultimo.json") -Value $marca -Encoding ASCII
    Write-Host "backup ok: $saida"
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
