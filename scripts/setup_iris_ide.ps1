# IRIS IDE (Theia) optional setup helper
param(
    [switch]$Repair
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$env:IRIS_IDE_DEMO = "0"
& "$Root\.venv\Scripts\python.exe" -c @"
from iris.system.iris_ide_runtime import IrisIdeRuntimeManager
mgr = IrisIdeRuntimeManager()
ok, msg = mgr.repair() if $Repair.IsPresent else mgr.install(progress=print)
print(msg)
raise SystemExit(0 if ok else 1)
"@
