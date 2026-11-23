#requires -Version 5.1
<#
Read-only offline-startup diagnostic. Tests the ORIGINAL PrintExp executable,
without injecting the 3D DLL, when -LaunchBaseline is explicitly supplied.
Any report written to disk stays inside the selected PrintExp installation.
#>
[CmdletBinding()]
param(
    [string]$PrintExpFolder = '',
    [switch]$LaunchBaseline
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($PrintExpFolder)) {
    $PrintExpFolder = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
}
$exe = Join-Path $PrintExpFolder 'PrintExp_X64.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "PrintExp_X64.exe does not exist at $PrintExpFolder"
}
$started = Get-Date
$lines = New-Object System.Collections.Generic.List[string]
function Note([string]$Value) {
    $script:lines.Add($Value)
    Write-Host $Value
}
Note "PrintExp offline startup diagnostic: $($started.ToString('u'))"
Note "Selected directory: $PrintExpFolder"
Note "Windows: $([Environment]::OSVersion.VersionString)"
Note "PowerShell x64: $([Environment]::Is64BitProcess)"
$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
Note "PrintExp_X64 SHA-256: $hash"
$config = Join-Path $PrintExpFolder 'Project.ini'
if (Test-Path -LiteralPath $config -PathType Leaf) {
    $match = [regex]::Match(
        [IO.File]::ReadAllText($config, [Text.Encoding]::Default),
        '(?im)^[ \t]*PROJECT_MODE[ \t]*=[ \t]*([0-9]+)')
    Note ("Project.ini PROJECT_MODE: " +
          $(if ($match.Success) { $match.Groups[1].Value } else { 'not found' }))
} else {
    Note "Project.ini: missing"
}
foreach ($module in @('mfc100u.dll','msvcr100.dll','msvcp100.dll','KLog.dll','DeviceManager.dll')) {
    $local = Join-Path $PrintExpFolder $module
    $system = Join-Path $env:WINDIR "System32\$module"
    $fromLocal = Test-Path -LiteralPath $local -PathType Leaf
    $fromSystem = Test-Path -LiteralPath $system -PathType Leaf
    Note ("Dependency {0}: app-folder={1}; System32={2}" -f
          $module,$fromLocal,$fromSystem)
}
if ($LaunchBaseline) {
    $running = @(Get-Process -Name PrintExp_X64 -ErrorAction SilentlyContinue)
    if ($running.Count) {
        Note "Baseline launch skipped: PrintExp_X64.exe is already running. Close it first."
    } else {
        Note "Launching the UNMODIFIED PrintExp executable, without the 3D DLL."
        try {
            $process = Start-Process -FilePath $exe -WorkingDirectory $PrintExpFolder -PassThru
            for ($attempt=0; $attempt -lt 100; ++$attempt) {
                Start-Sleep -Milliseconds 125
                $process.Refresh()
                if ($process.HasExited) { break }
            }
            if ($process.HasExited) {
                $signed = [int]$process.ExitCode
                $unsigned = [BitConverter]::ToUInt32([BitConverter]::GetBytes($signed),0)
                Note ("PrintExp EXITED during baseline check. Exit code: 0x{0:X8}" -f $unsigned)
                if ($unsigned -eq 0xC0000135) {
                    Note "0xC0000135 = STATUS_DLL_NOT_FOUND; check mfc100u.dll and VC++ 2010 x64."
                } elseif ($unsigned -eq 0xC0000005) {
                    Note "0xC0000005 = access violation; inspect Windows Application Error event."
                }
            } else {
                Note ("PrintExp is STILL RUNNING after baseline check. MainWindowHandle={0} Title={1}" -f
                      $process.MainWindowHandle,$process.MainWindowTitle)
                Note "The original process is intentionally left running; close it yourself."
            }
        } catch {
            Note "Baseline launch error: $($_.Exception.Message)"
        }
    }
    try {
        $events = Get-WinEvent -FilterHashtable @{
            LogName='Application'; Id=1000,1001;
            StartTime=$started.AddMinutes(-1)
        } -ErrorAction Stop |
          Where-Object { $_.Message -match 'PrintExp_X64|UV3DPage|mfc100u' } |
          Select-Object -First 6
        foreach ($event in $events) {
            Note ("Application Event ID={0} time={1}: {2}" -f
                  $event.Id,$event.TimeCreated,($event.Message -replace '\s+',' '))
        }
    } catch {
        Note "Windows Application Error event lookup unavailable or no matching event."
    }
}
$dir = Join-Path $PrintExpFolder 'UV3DAddOn\diagnostics'
try {
    [IO.Directory]::CreateDirectory($dir) | Out-Null
    $report = Join-Path $dir 'offline-startup-report.txt'
    [IO.File]::WriteAllLines($report,$lines,[Text.Encoding]::UTF8)
    Note "Report saved to: $report"
} catch {
    Note "Could not write inside the selected PrintExp directory: $($_.Exception.Message)"
    Note "The results above remain available in this PowerShell console."
}
