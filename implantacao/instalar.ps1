# Instala o Physis Hub num mini PC Windows 10/11 (PowerShell 5.1, como Administrador).
# Arquivo so com ASCII de proposito: o PowerShell 5.1 le .ps1 sem BOM como ANSI.
#
#   powershell -ExecutionPolicy Bypass -File instalar.ps1 -Pacote C:\entregas\physis-fazenda.zip -Firewall
#   ... -Modo nssm      # servico do Windows pelo NSSM (nssm.exe no PATH ou em C:\Physis\nssm.exe)
#   ... -Modo tarefa    # Agendador de Tarefas (padrao quando nao ha nssm): sobe ao ligar, reinicia se cair
#
# Idempotente. Codigo em C:\Physis\versoes\<data> com a juncao C:\Physis\atual; dados e segredos em
# %ProgramData%\Physis (so Administradores, SYSTEM e a conta LOCAL SERVICE, que roda o hub).
[CmdletBinding()]
param(
    [string]$Pacote = "",
    [string]$Python = "",
    [int]$Porta = 8700,
    [switch]$Firewall,
    [ValidateSet("", "nssm", "tarefa")][string]$Modo = ""
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3

function Msg($t) { Write-Host "==> $t" -ForegroundColor Green }
function Falha($t) { Write-Host "[erro] $t" -ForegroundColor Red; exit 1 }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Falha "abra o PowerShell como Administrador" }

$Aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$Raiz = "C:\Physis"
$Base = Join-Path $env:ProgramData "Physis"
$Dados = Join-Path $Base "dados"
$EnvF = Join-Path $Base "physis.env"
$Conta = "NT AUTHORITY\LocalService"

# 1. Python 3.10+
if (-not $Python) {
    foreach ($c in @("py", "python")) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) {
            $a = @("-c", "import sys; print(sys.executable)")
            if ($c -eq "py") { $a = @("-3") + $a }
            $exe = & $cmd.Source @a 2>$null
            if ($exe) { $Python = $exe.Trim(); break }
        }
    }
}
if (-not $Python -or -not (Test-Path $Python)) { Falha "Python 3.10+ nao encontrado; instale de python.org (para todos os usuarios) ou use -Python <caminho>" }
& $Python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { Falha "precisa de Python 3.10 ou mais novo ($Python)" }
if ($Python -like "*\Users\*") { Write-Warning "Python instalado so para um usuario ($Python): a conta LOCAL SERVICE pode nao enxergar. Prefira 'Install for all users'." }
Msg "Python: $Python"

# 2. Pacote
if (-not $Pacote) {
    if (Test-Path (Join-Path $Aqui "..\physis_hub\servidor.py")) { $Pacote = Join-Path $Aqui ".." }
    elseif (Test-Path (Join-Path $Aqui "..\physis-hub\physis_hub\servidor.py")) { $Pacote = Join-Path $Aqui "..\physis-hub" }
    else { Falha "use -Pacote <pasta ou .zip>" }
}
$tmp = $null
if ($Pacote -like "*.zip") {
    $tmp = Join-Path $env:TEMP ("physis-" + [guid]::NewGuid())
    Expand-Archive -Path $Pacote -DestinationPath $tmp
    $srv = Get-ChildItem -Path $tmp -Recurse -Filter servidor.py | Where-Object { $_.Directory.Name -eq "physis_hub" } | Select-Object -First 1
    if (-not $srv) { Falha "zip sem physis_hub\servidor.py" }
    $Pacote = $srv.Directory.Parent.FullName
}
if (-not (Test-Path (Join-Path $Pacote "physis_hub\servidor.py"))) { Falha "pacote sem physis_hub\servidor.py" }
$Pacote = (Resolve-Path $Pacote).Path

# 3. Pastas e permissoes
New-Item -ItemType Directory -Force -Path "$Raiz\versoes", $Dados, "$Dados\mapas", "$Dados\entregas", "$Dados\editais", "$Base\logs", "$Base\backups" | Out-Null
icacls $Base /inheritance:r /grant:r "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-19:(OI)(CI)RX" | Out-Null
icacls $Dados /grant:r "*S-1-5-19:(OI)(CI)M" | Out-Null
icacls "$Base\logs" /grant:r "*S-1-5-19:(OI)(CI)M" | Out-Null
icacls "$Base\backups" /inheritance:r /grant:r "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" | Out-Null

# 4. Codigo (versao nova so se mudou)
$atual = Join-Path $Raiz "atual"
$ver = Join-Path $Raiz ("versoes\" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Force -Path $ver | Out-Null
foreach ($item in @("physis_hub", "web", "tests", "docs", "instancia.json", "LICENSE", "LEIA-ME.md")) {
    $o = Join-Path $Pacote $item
    if (Test-Path $o) { Copy-Item -Recurse -Force -Path $o -Destination $ver }
}
if ((Test-Path "$atual\instancia.json") -and (Test-Path "$ver\instancia.json")) {
    Move-Item "$ver\instancia.json" "$ver\instancia.json.do-pacote" -Force
    Copy-Item "$atual\instancia.json" "$ver\instancia.json"
}
if (Test-Path $atual) { cmd /c rmdir "$atual" | Out-Null }
New-Item -ItemType Junction -Path $atual -Target $ver | Out-Null
New-Item -ItemType Directory -Force -Path "$Raiz\implantacao" | Out-Null
foreach ($f in @("backup.ps1", "verificar.ps1", "instalar.ps1")) {
    if ((Join-Path $Aqui $f) -ne (Join-Path "$Raiz\implantacao" $f)) { Copy-Item -Force (Join-Path $Aqui $f) "$Raiz\implantacao\" }
}
Msg "Codigo em $ver"

# 5. physis.env (sem segredos fixos; os que existirem sao gerados com python secrets)
if (-not (Test-Path $EnvF)) { Set-Content -Path $EnvF -Value "# Physis Hub - gerado por instalar.ps1. Nao versionar." -Encoding ASCII }
$linhas = @(Get-Content $EnvF)
function Garantir($k, $v) {
    if (-not ($script:linhas | Where-Object { $_ -match "^$k=" })) { $script:linhas += "$k=$v" }
}
Garantir "PHYSIS_BANCO" "$Dados\physis-hub.db"
Garantir "PHYSIS_PORTA" "$Porta"
Garantir "PHYSIS_ENDERECO" "0.0.0.0"
Garantir "PHYSIS_MAPAS" "$Dados\mapas"
Garantir "PHYSIS_ENTREGAS" "$Dados\entregas"
Garantir "PHYSIS_EDITAIS_PASTA" "$Dados\editais"
Garantir "PYTHONDONTWRITEBYTECODE" "1"
Set-Content -Path $EnvF -Value $linhas -Encoding ASCII
icacls $EnvF /inheritance:r /grant:r "*S-1-5-32-544:F" "*S-1-5-18:F" "*S-1-5-19:R" | Out-Null

# 6. Lancador: le o physis.env e sobe o hub (o ambiente fica no arquivo protegido, nao no registro)
$lancador = @"
`$ErrorActionPreference = 'Stop'
Get-Content '$EnvF' | Where-Object { `$_ -match '^[A-Z_][A-Z0-9_]*=' } | ForEach-Object {
    `$k, `$v = `$_ -split '=', 2; [Environment]::SetEnvironmentVariable(`$k, `$v, 'Process') }
Set-Location '$atual'
& '$Python' -m physis_hub.servidor *>> '$Base\logs\physis-hub.log'
exit `$LASTEXITCODE
"@
Set-Content -Path "$Raiz\iniciar-hub.ps1" -Value $lancador -Encoding ASCII
$ps = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$argsHub = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Raiz\iniciar-hub.ps1`""

# 7. Servico (NSSM) ou tarefa agendada
$nssm = (Get-Command nssm -ErrorAction SilentlyContinue)
if (-not $nssm -and (Test-Path "$Raiz\nssm.exe")) { $nssm = Get-Command "$Raiz\nssm.exe" }
if (-not $Modo) { $Modo = $(if ($nssm) { "nssm" } else { "tarefa" }) }
if ($Modo -eq "nssm") {
    if (-not $nssm) { Falha "nssm.exe nao encontrado (baixe de nssm.cc e coloque em C:\Physis\nssm.exe)" }
    $n = $nssm.Source
    if (-not (Get-Service PhysisHub -ErrorAction SilentlyContinue)) { & $n install PhysisHub $ps $argsHub | Out-Null }
    & $n set PhysisHub Application $ps | Out-Null
    & $n set PhysisHub AppParameters $argsHub | Out-Null
    & $n set PhysisHub DisplayName "Physis Hub" | Out-Null
    & $n set PhysisHub ObjectName $Conta | Out-Null
    & $n set PhysisHub Start SERVICE_AUTO_START | Out-Null
    & $n set PhysisHub AppStopMethodConsole 15000 | Out-Null
    & $n set PhysisHub AppExit Default Restart | Out-Null
    & $n set PhysisHub AppRestartDelay 5000 | Out-Null
    Restart-Service PhysisHub
    Msg "Servico PhysisHub (NSSM) ativo como LOCAL SERVICE"
} else {
    $acao = New-ScheduledTaskAction -Execute $ps -Argument $argsHub
    $gat = New-ScheduledTaskTrigger -AtStartup
    $quem = New-ScheduledTaskPrincipal -UserId "LOCALSERVICE" -LogonType ServiceAccount
    $cfg = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName "PhysisHub" -Action $acao -Trigger $gat -Principal $quem -Settings $cfg -Force | Out-Null
    Stop-ScheduledTask -TaskName "PhysisHub" -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName "PhysisHub"
    Msg "Tarefa PhysisHub registrada (sobe ao ligar, como LOCAL SERVICE)"
}

# 8. Copia diaria (as 02:30, como SYSTEM; precisa de %ProgramData%\Physis\backup.env)
$acaoB = New-ScheduledTaskAction -Execute $ps -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Raiz\implantacao\backup.ps1`""
$gatB = New-ScheduledTaskTrigger -Daily -At "02:30"
$quemB = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName "PhysisBackup" -Action $acaoB -Trigger $gatB -Principal $quemB `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable) -Force | Out-Null
if (-not (Test-Path "$Base\backup.env")) { Write-Warning "copia diaria registrada, mas falta $Base\backup.env (modelo: implantacao\backup.env.exemplo)" }

# 9. Firewall: porta do hub so para a sub-rede local, perfis Privado/Dominio
if ($Firewall) {
    Get-NetFirewallRule -DisplayName "Physis Hub" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName "Physis Hub" -Direction Inbound -Protocol TCP -LocalPort $Porta `
        -RemoteAddress LocalSubnet -Profile Private, Domain -Action Allow | Out-Null
    Msg "Firewall: porta $Porta aberta so para a rede local (perfil Privado). Marque a rede do cliente como Privada."
}
if ($tmp) { Remove-Item -Recurse -Force $tmp }
Start-Sleep -Seconds 4
& (Join-Path $Aqui "verificar.ps1")
Msg "Pronto. Abra http://<ip deste PC>:$Porta/ e crie a primeira conta pela rede local."
