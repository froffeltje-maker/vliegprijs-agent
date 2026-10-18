# Maakt in Windows Taakplanner een taak die de vliegprijs-agent elke 2 uur draait
# met config.thuis.json (alle luchthavens binnen 2 uur van Zwolle).
# Uitvoeren: rechtsklik op dit bestand > "Uitvoeren met PowerShell".

$ErrorActionPreference = "Stop"
$map = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "Python niet gevonden. Installeer Python via https://www.python.org (vink 'Add to PATH' aan)." }

& $python -m pip install -r (Join-Path $map "requirements.txt")
New-Item -ItemType Directory -Force -Path (Join-Path $map "data-thuis") | Out-Null

$actie = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"`"$python`" zoek.py --config config.thuis.json >> data-thuis\run.log 2>&1`"" `
    -WorkingDirectory $map
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Hours 2)
$instellingen = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName "Vliegprijs-agent" -Action $actie -Trigger $trigger `
    -Settings $instellingen -Force | Out-Null

Write-Host "Klaar. De agent draait over 2 minuten voor het eerst en daarna elke 2 uur."
Write-Host "Resultaten: $map\RAPPORT-thuis.md   Logboek: $map\data-thuis\run.log"
Write-Host "Stoppen: Taakplanner openen > taak 'Vliegprijs-agent' > Uitschakelen."
