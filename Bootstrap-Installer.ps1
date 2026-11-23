#requires -Version 5.1
<#
.Purpose
  First-run bootstrap for the PrintExp 3D add-on. Uses Windows' built-in PowerShell
  and Windows Forms; Python and Git are *not* needed to open this screen.
  No vendor files are modified here.
#>
[CmdletBinding()]
param([switch]$CheckOnly, [string]$WorkerRequest = "")

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:Python = $null
$script:Git = $null
$script:Compiler = $null
$script:Winget = $null
$script:Form = $null
$script:LogBox = $null
$script:StatusLabel = $null
$script:ContinueButton = $null
$script:BuildToolsCheckbox = $null
$script:BuildToolsPath = $null
$script:WorkerLog = $null
$script:PrintExpPath = $null
$script:UpdateButton = $null
$script:SelectionFile = Join-Path $env:LOCALAPPDATA 'PrintExp3DAddOn\selected-install.txt'

# Installer binaries must come from identified, trusted publishers. This fixed
# Python fallback is a PSF-published Windows installer with a published checksum;
# WinGet remains preferred and receives updates from its package manifests.
$script:PythonFallbackUrl = 'https://www.python.org/ftp/python/3.13.14/python-3.13.14-amd64.exe'
$script:PythonFallbackSha256 = 'c54d9b9bbb8a36e6489363ddd01139707fd781d72f1f9e90c7ec65d0061368e0'
$script:BuildToolsUrl = 'https://aka.ms/vs/17/release/vs_BuildTools.exe'

function Resolve-Python {
    $candidates = New-Object System.Collections.Generic.List[object]
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { $candidates.Add(@($py.Source, @('-3'))) }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) { $candidates.Add(@($python.Source, @())) }
    foreach ($parent in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles\Python")) {
        if (Test-Path -LiteralPath $parent) {
            Get-ChildItem -LiteralPath $parent -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue | ForEach-Object {
                $p = Join-Path $_.FullName 'python.exe'
                if (Test-Path -LiteralPath $p) { $candidates.Add(@($p, @())) }
            }
        }
    }
    foreach ($candidate in $candidates) {
        $exe = [string]$candidate[0]
        $prefix = @($candidate[1])
        try {
            $output = & $exe @prefix -c 'import sys,tkinter; assert sys.version_info >= (3,10); print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $output) {
                $resolved = ([string]($output | Select-Object -Last 1)).Trim()
                if (Test-Path -LiteralPath $resolved) { return $resolved }
            }
        } catch { }
    }
    return $null
}

function Resolve-Git {
    $candidates = @(
        (Get-Command git.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Join-Path $env:ProgramFiles 'Git\cmd\git.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Git\cmd\git.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Git\cmd\git.exe')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    foreach ($candidate in $candidates) {
        try {
            $null = & $candidate --version 2>$null
            if ($LASTEXITCODE -eq 0) { return [string]$candidate }
        } catch { }
    }
    return $null
}

function Resolve-Compiler {
    $cl = Get-Command cl.exe -ErrorAction SilentlyContinue
    if ($cl) { return $cl.Source }
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswhere) {
        try {
            $paths = @(& $vswhere -products '*' -requires 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64' -property installationPath 2>$null)
            foreach ($path in $paths) {
                if (Test-Path -LiteralPath (Join-Path $path 'VC\Auxiliary\Build\vcvars64.bat')) { return $path }
            }
        } catch { }
    }
    return $null
}

function Resolve-Winget {
    $cmd = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Refresh-Environment {
    # System-wide and per-user PATH changes are not inherited by an already-running process.
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Refresh-Status {
    Refresh-Environment
    $script:Python = Resolve-Python
    $script:Git = Resolve-Git
    $script:Compiler = Resolve-Compiler
    $script:Winget = Resolve-Winget
}

# A fresh computer has no saved folder. Test-Path -LiteralPath '' raises
# ParameterArgumentValidationErrorEmptyString before the Browse dialog opens.
function Test-ExistingDirectory([AllowEmptyString()][string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    try {
        return [bool](Test-Path -LiteralPath $Path -PathType Container -ErrorAction Stop)
    } catch {
        return $false
    }
}

function Test-VC2010X64Runtime([string]$InstallFolder) {
    # PrintExp_X64.exe is a 64-bit VC++ 2010 MFC application and imports
    # mfc100u.dll, NOT the mfc100.dll bundled in the vendor folder.
    $locations = @((Join-Path $env:WINDIR 'System32\mfc100u.dll'))
    if (-not [string]::IsNullOrWhiteSpace($InstallFolder)) {
        $locations += (Join-Path $InstallFolder 'mfc100u.dll')
    }
    foreach ($path in $locations) {
        if (Test-Path -LiteralPath $path -PathType Leaf) { return $true }
    }
    return $false
}

function Ensure-VC2010X64Runtime([string]$InstallFolder) {
    if (Test-VC2010X64Runtime $InstallFolder) {
        Log-Message 'Visual C++ 2010 x64 MFC runtime already present.'
        return
    }
    Log-Message 'PrintExp requires the missing Visual C++ 2010 SP1 x64 MFC runtime (mfc100u.dll).'
    # Prefer Microsoft-maintained WinGet package manifests. Do not use
    # unverified third-party single DLL download sites.
    $script:Winget = Resolve-Winget
    if ($script:Winget) {
        $null = Install-UsingWinget 'Microsoft.VCRedist.2010.x64'
    }
    if (-not (Test-VC2010X64Runtime $InstallFolder)) {
        $download = Join-Path $env:TEMP 'PrintExp3D-vcredist2010_x64.exe'
        # Microsoft Learn: "Visual Studio 2010 (VC++ 10.0) SP1", x64.
        $official = 'https://download.microsoft.com/download/1/6/5/165255E7-1014-4D0A-B094-B6A430A6BFFC/vcredist_x64.exe'
        Download-Official $official $download
        Confirm-Authenticode $download 'Microsoft Corporation'
        [void](Invoke-CheckedProcess -File $download -ProcessArguments @('/q','/norestart') -Name 'Microsoft Visual C++ 2010 SP1 x64')
    }
    if (-not (Test-VC2010X64Runtime $InstallFolder)) {
        throw 'The required 64-bit mfc100u.dll is still missing. Windows may need to restart after the Microsoft runtime installation.'
    }
    Log-Message 'Verified Visual C++ 2010 x64 MFC runtime after installation.'
}

function Prebuilt-NativeFilesExist {
    return (Test-Path -LiteralPath (Join-Path $script:Root 'dist\windows\PrintExp3DLauncher.exe')) -and
           (Test-Path -LiteralPath (Join-Path $script:Root 'dist\windows\UV3DPage.dll'))
}

function Log-Message([string]$Message) {
    if ($script:LogBox) {
        $script:LogBox.AppendText("$Message`r`n")
        $script:LogBox.SelectionStart = $script:LogBox.TextLength
        $script:LogBox.ScrollToCaret()
        [System.Windows.Forms.Application]::DoEvents()
    } elseif ($script:WorkerLog) {
        [IO.File]::AppendAllText($script:WorkerLog, "$Message`r`n", [Text.Encoding]::UTF8)
    } else { Write-Host $Message }
}

function Invoke-CheckedProcess([string]$File, [string[]]$ProcessArguments, [string]$Name) {
    Log-Message "Starting $Name. Windows may ask for administrator approval."
    # No strings derived from download output are ever passed to a shell.
    $p = Start-Process -FilePath $File -ArgumentList $ProcessArguments -PassThru
    while (-not $p.HasExited) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 350
        $p.Refresh()
    }
    $exit = $p.ExitCode
    if ($exit -ne 0 -and $exit -ne 3010) {
        throw "$Name exited with code $exit. The install was not completed."
    }
    if ($exit -eq 3010) { Log-Message "$Name needs a Windows restart before all components are ready." }
    return $exit
}

function Install-UsingWinget([string]$Id) {
    if (-not $script:Winget) { return $false }
    Log-Message "Downloading and installing $Id using Windows Package Manager..."
    try {
        $installArgs = @('install','--id',$Id,'--exact','--source','winget','--silent',
                  '--accept-source-agreements','--accept-package-agreements','--disable-interactivity')
        [void](Invoke-CheckedProcess -File $script:Winget -ProcessArguments $installArgs -Name $Id)
        return $true
    } catch {
        Log-Message "WinGet could not install ${Id}: $($_.Exception.Message)"
        return $false
    }
}

function Download-Official([string]$Uri, [string]$Destination) {
    if (-not $Uri.StartsWith('https://', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Only HTTPS downloads are permitted.'
    }
    Log-Message "Downloading $(Split-Path -Leaf $Destination)..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Uri -OutFile $Destination -UseBasicParsing -MaximumRedirection 6
    if (-not (Test-Path -LiteralPath $Destination) -or (Get-Item $Destination).Length -lt 100000) {
        throw 'Download is missing or unexpectedly short.'
    }
}

function Confirm-Authenticode([string]$Path, [string]$Publisher) {
    $sig = Get-AuthenticodeSignature -LiteralPath $Path
    if ($sig.Status -ne 'Valid' -or -not $sig.SignerCertificate -or
        $sig.SignerCertificate.Subject -notmatch $Publisher) {
        throw "Refusing to run an installer with a missing, invalid, or unexpected publisher signature: $(Split-Path -Leaf $Path)."
    }
}

function Install-PythonFallback {
    $download = Join-Path $env:TEMP 'uv3d-python-3.13.14-amd64.exe'
    Download-Official $script:PythonFallbackUrl $download
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $download).Hash.ToLowerInvariant() -ne $script:PythonFallbackSha256) {
        throw 'Official Python installer SHA-256 mismatch. Refusing to execute.'
    }
    Confirm-Authenticode $download 'Python Software Foundation'
    [void](Invoke-CheckedProcess -File $download -ProcessArguments @('/quiet','InstallAllUsers=0','PrependPath=1',
                                             'Include_tcltk=1','Include_pip=1','Include_test=0','/norestart') -Name 'Python 3.13')
}

function Install-GitFallback {
    Log-Message 'Finding the current signed Git for Windows installer on the official release page...'
    $headers = @{'User-Agent'='PrintExp-3D-Addon-Bootstrap'}
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/git-for-windows/git/releases/latest' -Headers $headers
    $asset = $release.assets | Where-Object { $_.name -match '^Git-[0-9].*-64-bit\.exe$' } | Select-Object -First 1
    if (-not $asset -or -not $asset.browser_download_url -or
        -not $asset.browser_download_url.StartsWith('https://github.com/git-for-windows/git/releases/download/')) {
        throw 'The official Git for Windows release did not provide the expected x64 installer.'
    }
    $download = Join-Path $env:TEMP 'uv3d-git-for-windows-amd64.exe'
    Download-Official $asset.browser_download_url $download
    Confirm-Authenticode $download 'Git for Windows|Open Source Developer|GitHub'
    [void](Invoke-CheckedProcess -File $download -ProcessArguments @('/VERYSILENT','/NORESTART','/SUPPRESSMSGBOXES','/SP-') -Name 'Git for Windows')
}

function Install-Compiler {
    $download = Join-Path $env:TEMP 'uv3d-vs-2022-buildtools.exe'
    Download-Official $script:BuildToolsUrl $download
    Confirm-Authenticode $download 'Microsoft Corporation'
    Log-Message 'The Microsoft C++ toolchain is large (potentially several gigabytes).'
    $arguments = @('--quiet','--wait','--norestart','--add',
                   'Microsoft.VisualStudio.Workload.VCTools','--includeRecommended')
    $location = if (Test-Path -LiteralPath 'X:\') { 'X:\VisualStudioBuildTools' } else { '' }
    if ($location) {
        # Start-Process joins the argument array; quote paths containing spaces explicitly.
        $arguments += @('--installPath', ('"' + $location + '"'))
    }
    [void](Invoke-CheckedProcess -File $download -ProcessArguments $arguments -Name 'Visual Studio C++ Build Tools')
}

if ($CheckOnly) {
    if (Test-ExistingDirectory '') { throw 'Empty directory path guard failed.' }
    Refresh-Status
    Write-Output "Python=$([bool]$script:Python)"
    Write-Output "Git=$([bool]$script:Git)"
    Write-Output "MSVC=$([bool]$script:Compiler)"
    Write-Output "VC2010_x64=$([bool](Test-VC2010X64Runtime ''))"
    exit 0
}

# This is the only user-facing window. Worker mode is a hidden, elevated process,
# never a second installer window.
function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Python {
    Refresh-Status
    if (-not $script:Python) {
        Log-Message 'Installing missing Python 3...'
        if (Install-UsingWinget 'Python.Python.3.13') { Refresh-Status }
        if (-not $script:Python) { Install-PythonFallback; Refresh-Status }
    }
    if (-not $script:Python) { throw 'Python 3 with Tkinter is unavailable after installation. Restart Windows and try again.' }
}

function Ensure-Git {
    Refresh-Status
    if (-not $script:Git) {
        Log-Message 'Installing missing Git for Windows...'
        if (Install-UsingWinget 'Git.Git') { Refresh-Status }
        if (-not $script:Git) { Install-GitFallback; Refresh-Status }
    }
    if (-not $script:Git) { throw 'Git for Windows is unavailable after installation. Restart Windows and try again.' }
    $env:Path = "$(Split-Path -Parent $script:Git);$env:Path"
}

function Ensure-CompilerIfNeeded([string]$Action, [string]$InstallFolder) {
    $installedBinaries = (Test-Path -LiteralPath (Join-Path $InstallFolder 'UV3DAddOn\dist\windows\PrintExp3DLauncher.exe')) -and
        (Test-Path -LiteralPath (Join-Path $InstallFolder 'UV3DAddOn\dist\windows\UV3DPage.dll'))
    if ($installedBinaries -or (Prebuilt-NativeFilesExist)) { return }
    Refresh-Status
    if (-not $script:Compiler) {
        Log-Message 'Native binaries are not prebuilt. Installing Microsoft C++ Build Tools (large download)...'
        Install-Compiler
        Refresh-Status
    }
    if (-not $script:Compiler) { throw 'Microsoft C++ Build Tools could not be detected after installation. Restart Windows and try again.' }
}

function Run-ElevatedAction([string]$Action, [string]$InstallFolder) {
    if (-not (Test-Administrator)) { throw 'Administrator permission is required for Install, Update and Uninstall.' }
    if ($Action -notin @('install','update','uninstall','offline-enable','offline-disable','vc2010-install','simulate-enable','simulate-disable')) { throw 'Unsupported modification action.' }
    if (-not (Test-Path -LiteralPath (Join-Path $InstallFolder 'PrintExp_X64.exe'))) {
        throw 'Select the folder that contains PrintExp_X64.exe.'
    }
    if ($Action -eq 'install' -and (Test-Path -LiteralPath (Join-Path $InstallFolder 'UV3DAddOn'))) {
        throw 'The add-on already exists. Use Update from main instead.'
    }
    if ($Action -eq 'update' -and -not (Test-Path -LiteralPath (Join-Path $InstallFolder 'UV3DAddOn\.uv3d-managed-install.json'))) {
        throw 'No managed add-on is installed. Use Install Add-on first.'
    }
    if ($Action -in @('offline-enable','offline-disable','simulate-enable','simulate-disable') -and
        -not (Test-Path -LiteralPath (Join-Path $InstallFolder 'UV3DAddOn\.uv3d-managed-install.json'))) {
        throw 'Install the add-on before enabling offline development mode.'
    }
    if ($Action -eq 'vc2010-install') {
        # Installing a Microsoft system prerequisite requires UAC. This is
        # explicitly approved by the user; vendor PrintExp files aren't edited.
        Ensure-VC2010X64Runtime $InstallFolder
        return
    }
    # Offline configuration and uninstall require Python only.
    Ensure-Python
    if ($Action -in @('install','update')) {
        Ensure-Git
        Ensure-CompilerIfNeeded $Action $InstallFolder
    }
    Log-Message "Running $Action in the selected PrintExp directory..."
    $actionScript = Join-Path $script:Root 'addon_action.py'
    & $script:Python $actionScript --action $Action --target $InstallFolder --log-file $script:WorkerLog
    if ($LASTEXITCODE -ne 0) { throw "Add-on $Action failed (exit $LASTEXITCODE). See the operation log." }
}

function Invoke-Worker([string]$RequestFile) {
    $request = Get-Content -LiteralPath $RequestFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $script:WorkerLog = [string]$request.log
    $resultPath = [string]$request.result
    $result = @{ success = $false; message = 'Unknown error' }
    try {
        Log-Message "Starting $($request.action)..."
        Run-ElevatedAction ([string]$request.action) ([string]$request.folder)
        $result.success = $true
        $result.message = "$(($request.action).ToUpperInvariant()) completed successfully."
        Log-Message $result.message
    } catch {
        $result.message = $_.Exception.Message
        Log-Message "ERROR: $($result.message)"
    } finally {
        $result | ConvertTo-Json -Compress | Set-Content -LiteralPath $resultPath -Encoding UTF8
    }
    if (-not $result.success) { exit 1 }
    exit 0
}

if ($WorkerRequest) {
    Add-Type -AssemblyName System.Windows.Forms
    Invoke-Worker $WorkerRequest
}

if (-not [Environment]::Is64BitOperatingSystem) { throw 'PrintExp 3D requires a 64-bit Windows installation.' }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$script:PreferenceFolder = Join-Path $env:LOCALAPPDATA 'PrintExp3DAddOn'
$script:PreferenceFile = Join-Path $script:PreferenceFolder 'selected-install.txt'
$script:SavedLogFile = Join-Path $script:PreferenceFolder 'last-operation.log'
$script:WorkerProcess = $null
$script:RequestDirectory = $null
$script:CurrentAction = $null
$script:WorkerStatus = $null
$script:StatusLabel = $null

function Read-Selection {
    try {
        if (Test-Path -LiteralPath $script:PreferenceFile) {
            return [IO.File]::ReadAllText($script:PreferenceFile, [Text.Encoding]::UTF8).Trim([char]0xFEFF).Trim()
        }
    } catch { }
    return ''
}

function Save-Selection([string]$Selection) {
    $selected = $Selection.Trim()
    if (-not $selected -or -not (Test-Path -LiteralPath (Join-Path $selected 'PrintExp_X64.exe'))) { return }
    [IO.Directory]::CreateDirectory($script:PreferenceFolder) | Out-Null
    [IO.File]::WriteAllText($script:PreferenceFile, $selected, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-SelectedFolder {
    $selected = $script:FolderInput.Text.Trim()
    if (-not $selected -or -not (Test-Path -LiteralPath (Join-Path $selected 'PrintExp_X64.exe'))) {
        throw 'Choose the PrintExp installation folder containing PrintExp_X64.exe.'
    }
    Save-Selection $selected
    return [IO.Path]::GetFullPath($selected)
}

function Set-Busy([bool]$Busy) {
    foreach ($button in @($script:InstallButton,$script:UpdateButton,$script:UninstallButton,$script:LaunchButton,$script:BrowseButton,$script:SimulationCheck)) {
        $button.Enabled = -not $Busy
    }
    $script:FolderInput.ReadOnly = $Busy
}

function Begin-Modification([string]$Action) {
    if ($script:WorkerProcess) { return }
    try {
        $folder = Get-SelectedFolder
        # Do NOT inspect the old marker as an unelevated user. A previous
        # installer copied private administrator TEMP permissions into the
        # add-on folder, so Test-Path can wrongly report the marker missing.
        # Validation belongs to the elevated worker after UAC approval.
        # Existing installations and restrictive ACLs are checked by the
        # elevated worker rather than a low-privilege preflight.
        # UAC is requested on EVERY modification, not only if a write probe fails.
        $dir = Join-Path $env:TEMP ('PrintExp3D-'+[guid]::NewGuid().ToString('N'))
        [IO.Directory]::CreateDirectory($dir) | Out-Null
        $script:RequestDirectory = $dir
        $requestFile = Join-Path $dir 'request.json'
        $resultFile = Join-Path $dir 'result.json'
        $logFile = Join-Path $dir 'operation.log'
        @{ action = $Action; folder = $folder; log = $logFile; result = $resultFile } |
            ConvertTo-Json -Compress | Set-Content -LiteralPath $requestFile -Encoding UTF8
        $script:WorkerResult = $resultFile
        $script:WorkerLog = $logFile
        $script:CurrentAction = $Action
        $script:OperationFolder = $folder
        $script:WorkerStatus = 'Requesting administrator permission...'
        $script:StatusLabel.Text = $script:WorkerStatus
        # ShellExecute 'runas' displays the standard Windows UAC approval dialog.
        # The worker itself is hidden; the existing manager window stays visible.
        $arguments = '-NoProfile -NonInteractive -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -WorkerRequest "{1}"' -f $PSCommandPath, $requestFile
        $script:WorkerProcess = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden -PassThru -ErrorAction Stop
        Set-Busy $true
    } catch {
        $script:StatusLabel.Text = 'Not started: ' + $_.Exception.Message
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'PrintExp 3D', 'OK', 'Error') | Out-Null
        $script:WorkerProcess = $null
        if ($script:RequestDirectory) {
            Remove-Item -LiteralPath $script:RequestDirectory -Recurse -Force -ErrorAction SilentlyContinue
            $script:RequestDirectory = $null
        }
    }
}

function Test-UserCanReadInstalledFiles([string]$InstallFolder) {
    # This runs in the ORIGINAL, non-elevated UI account. A successful elevated
    # installation can still be unusable when files inherit restrictive ACLs.
    # Confirm that the regular user can read every critical installed component.
    $required = @(
        'Start PrintExp with 3D.cmd',
        'UV3DAddOn\.uv3d-managed-install.json',
        'UV3DAddOn\dist\windows\PrintExp3DLauncher.exe',
        'UV3DAddOn\dist\windows\UV3DPage.dll',
        'UV3DAddOn\addon_manager_core.py',
        'UV3DAddOn\src\native\Stage1Launcher.cpp',
        'UV3DAddOn\src\native\Stage1Page.cpp'
    )
    foreach ($relative in $required) {
        $path = Join-Path $InstallFolder $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Post-install check failed: missing or inaccessible $relative"
        }
        try {
            # The checksum operation requires read access and catches ACL issues.
            # It also confirms the file isn't an empty placeholder.
            $item = Get-Item -LiteralPath $path -ErrorAction Stop
            if ($item.Length -eq 0) { throw "Empty file: $relative" }
            $null = Get-FileHash -LiteralPath $path -Algorithm SHA256 -ErrorAction Stop
        } catch {
            throw "Post-install check failed: cannot read $relative. $($_.Exception.Message)"
        }
    }
}

function Finish-Modification {
    $success = $false
    $message = 'The elevated worker exited without a result. An administrator account may not have access to the request folder, or Windows blocked the process. The original PrintExp files have not been intentionally modified. Check %LOCALAPPDATA%\PrintExp3DAddOn\last-operation.log if available.'
    try {
        if (Test-Path -LiteralPath $script:WorkerResult) {
            $value = Get-Content -LiteralPath $script:WorkerResult -Raw -Encoding UTF8 | ConvertFrom-Json
            $success = [bool]$value.success
            $message = [string]$value.message
            if ($success -and $script:CurrentAction -in @('install','update')) {
                # A second check after the elevated worker exits, using the
                # regular user's permissions. Don't report success prematurely.
                try {
                    Test-UserCanReadInstalledFiles $script:OperationFolder
                    $message += ' Post-install verification passed (files readable by your Windows account).'
                } catch {
                    $success = $false
                    $message = $_.Exception.Message + ' Add-on files were not deleted. Review the operation log.'
                }
            }
        }
        if (Test-Path -LiteralPath $script:WorkerLog) {
            [IO.Directory]::CreateDirectory($script:PreferenceFolder) | Out-Null
            Copy-Item -LiteralPath $script:WorkerLog -Destination $script:SavedLogFile -Force
        }
    } catch { $message = "Unable to read worker result: $($_.Exception.Message)" }
    Set-Busy $false
    $script:WorkerProcess = $null
    $script:StatusLabel.Text = $message
    if ($script:RequestDirectory) {
        Remove-Item -LiteralPath $script:RequestDirectory -Recurse -Force -ErrorAction SilentlyContinue
        $script:RequestDirectory = $null
    }
    $icon = if ($success) {'Information'} else {'Error'}
    [System.Windows.Forms.MessageBox]::Show($message, 'PrintExp 3D', 'OK', $icon) | Out-Null
    # The UI bootstrap lives outside UV3DAddOn when started from an older
    # ZIP. Install/Update has fetched the new manager as part of the add-on.
    # Reopen that manager now so newly added controls appear immediately.
    if ($success -and $script:CurrentAction -in @('install','update')) {
        $latest = Join-Path $script:OperationFolder 'UV3DAddOn\Start-Installer.vbs'
        if (Test-Path -LiteralPath $latest -PathType Leaf) {
            $latestRoot = [IO.Path]::GetFullPath((Split-Path -Parent $latest)).TrimEnd('\')
            try {
                # Restart even when we were already running from UV3DAddOn;
                # the updated PowerShell file cannot refresh the current
                # in-memory WinForms controls without reopening the manager.
                $script:StatusLabel.Text = 'Opening the updated add-on manager...'
                Start-Process -FilePath 'wscript.exe' -ArgumentList ('"{0}"' -f $latest) -WorkingDirectory $latestRoot -ErrorAction Stop
                $form.Close()
                return
            } catch {
                $script:StatusLabel.Text = 'The add-on updated, but the new manager could not open: ' + $_.Exception.Message
            }
        }
    }
    if ($success -and $script:CurrentAction -in @('offline-enable','vc2010-install','simulate-enable','simulate-disable')) {
        try {
            if ($script:SimulationCheck -and $script:SimulationCheck.Checked) {
                Start-SimulatedPrintExp $script:OperationFolder
            } else {
                Start-NativePrintExp $script:OperationFolder
            }
        }
        catch {
            $script:StatusLabel.Text = $_.Exception.Message
            [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'PrintExp 3D', 'OK', 'Error') | Out-Null
        }
    }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = 'PrintExp 3D Add-on Manager'
# ClientSize is the usable area INSIDE the title bar, unlike Size. Give the
# checkbox and multiline status enough room at Windows 125-200% scaling.
$form.ClientSize = New-Object System.Drawing.Size(744,320)
$form.MinimumSize = New-Object System.Drawing.Size(760,365)
$form.MaximumSize = New-Object System.Drawing.Size(1200,510)
$form.AutoScroll = $true
$form.StartPosition = 'CenterScreen'
$form.Font = New-Object System.Drawing.Font('Segoe UI',10)
$form.BackColor = [System.Drawing.Color]::FromArgb(24,33,43)
$form.ForeColor = [System.Drawing.Color]::White

$title = New-Object System.Windows.Forms.Label
$title.Text = 'PrintExp · 3D Add-on'
$title.Font = New-Object System.Drawing.Font('Segoe UI Semibold',16)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(20,17)
$form.Controls.Add($title)

$folderLabel = New-Object System.Windows.Forms.Label
$folderLabel.Text = 'PrintExp installation folder'
$folderLabel.Location = New-Object System.Drawing.Point(20,65)
$folderLabel.AutoSize = $true
$form.Controls.Add($folderLabel)

$script:FolderInput = New-Object System.Windows.Forms.TextBox
$script:FolderInput.Text = Read-Selection
$script:FolderInput.Location = New-Object System.Drawing.Point(20,90)
$script:FolderInput.Size = New-Object System.Drawing.Size(600,27)
$script:FolderInput.Anchor = 'Top,Left,Right'
$form.Controls.Add($script:FolderInput)

$script:BrowseButton = New-Object System.Windows.Forms.Button
$script:BrowseButton.Text = 'Browse...'
$script:BrowseButton.Location = New-Object System.Drawing.Point(631,88)
$script:BrowseButton.Size = New-Object System.Drawing.Size(105,32)
$script:BrowseButton.Anchor = 'Top,Right'
$form.Controls.Add($script:BrowseButton)
$script:BrowseButton.Add_Click({
    $picker = New-Object System.Windows.Forms.FolderBrowserDialog
    $picker.Description = 'Select the folder containing PrintExp_X64.exe'
    $picker.ShowNewFolderButton = $false
    $previousSelection = [string]$script:FolderInput.Text
    if (Test-ExistingDirectory $previousSelection) { $picker.SelectedPath = $previousSelection }
    if ($picker.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $script:FolderInput.Text = $picker.SelectedPath
        Save-Selection $picker.SelectedPath
        if ($script:SimulationCheck) {
            $script:SimulationCheck.Checked = Test-SimulationProfile $picker.SelectedPath
        }
    }
})
$script:FolderInput.Add_Leave({ Save-Selection $script:FolderInput.Text; if ($script:SimulationCheck) { $script:SimulationCheck.Checked = Test-SimulationProfile $script:FolderInput.Text } })

$script:InstallButton = New-Object System.Windows.Forms.Button
$script:InstallButton.Text = 'Install Add-on'
$script:InstallButton.Location = New-Object System.Drawing.Point(20,137)
$script:InstallButton.Size = New-Object System.Drawing.Size(158,39)
$form.Controls.Add($script:InstallButton)
$script:InstallButton.Add_Click({ Begin-Modification 'install' })

$script:UpdateButton = New-Object System.Windows.Forms.Button
$script:UpdateButton.Text = 'Update from main'
$script:UpdateButton.Location = New-Object System.Drawing.Point(187,137)
$script:UpdateButton.Size = New-Object System.Drawing.Size(158,39)
$form.Controls.Add($script:UpdateButton)
$script:UpdateButton.Add_Click({ Begin-Modification 'update' })

$script:UninstallButton = New-Object System.Windows.Forms.Button
$script:UninstallButton.Text = 'Uninstall Add-on'
$script:UninstallButton.Location = New-Object System.Drawing.Point(354,137)
$script:UninstallButton.Size = New-Object System.Drawing.Size(158,39)
$form.Controls.Add($script:UninstallButton)
$script:UninstallButton.Add_Click({ Begin-Modification 'uninstall' })

function Read-ProjectMode([string]$InstallFolder) {
    $config = Join-Path $InstallFolder 'Project.ini'
    if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
        throw 'Project.ini is missing from the selected PrintExp installation.'
    }
    # The file may contain GBK-encoded Chinese comments; the ASCII key and
    # value are safe to inspect without changing its original bytes.
    $raw = [IO.File]::ReadAllText($config, [Text.Encoding]::Default)
    $section = [regex]::Match($raw, '(?ims)^\s*\[PROJECT_CONFIG\]\s*(.*?)(?=^\s*\[|\z)')
    if (-not $section.Success) { throw 'Project.ini has no [PROJECT_CONFIG] section.' }
    $mode = [regex]::Match($section.Groups[1].Value,
        '(?im)^[ \t]*PROJECT_MODE[ \t]*=[ \t]*([01])(?=$|[ \t;#])')
    if (-not $mode.Success) { throw 'Project.ini has no PROJECT_MODE=0/1 setting.' }
    return [int]$mode.Groups[1].Value
}

function Test-SimulationProfile([string]$InstallFolder) {
    if ([string]::IsNullOrWhiteSpace($InstallFolder)) { return $false }
    $config = Join-Path $InstallFolder 'Project.ini'
    if (-not (Test-Path -LiteralPath $config -PathType Leaf)) { return $false }
    try {
        $data = [IO.File]::ReadAllText($config, [Text.Encoding]::Default)
        $mode = [regex]::IsMatch($data, '(?im)^[ \t]*PROJECT_MODE[ \t]*=[ \t]*1[ \t\r]*$')
        $ipCount = [regex]::Matches($data,
            '(?im)^[ \t]*ServerIP[ \t]*=[ \t]*127\.0\.0\.1[ \t\r]*$').Count
        return ($mode -and $ipCount -ge 2)
    } catch { return $false }
}

function Start-SimulatedPrintExp([string]$InstallFolder) {
    if (-not (Test-SimulationProfile $InstallFolder)) {
        throw 'Simulation requires the redirected Project.ini. Approve UAC setup first.'
    }
    if (-not (Test-VC2010X64Runtime $InstallFolder)) {
        $decision = [System.Windows.Forms.MessageBox]::Show(
            'PrintExp requires Microsoft Visual C++ 2010 SP1 x64. Install this free runtime?',
            'Microsoft runtime required', 'YesNo', 'Question')
        if ($decision -ne [System.Windows.Forms.DialogResult]::Yes) { return }
        Begin-Modification 'vc2010-install'
        return
    }
    Refresh-Status
    if (-not $script:Python) {
        throw 'Python is required for the virtual controller. Use Update from main to install dependencies.'
    }
    $virtual = Join-Path $InstallFolder 'UV3DAddOn\simulated_controller.py'
    $launcher = Join-Path $InstallFolder 'UV3DAddOn\dist\windows\PrintExp3DLauncher.exe'
    $hostExe = Join-Path $InstallFolder 'PrintExp_X64.exe'
    $log = Join-Path $InstallFolder 'UV3DAddOn\diagnostics\simulated-controller.ndjson'
    foreach ($required in @($virtual,$launcher,$hostExe)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Simulation file missing: $required. Run Update from main."
        }
    }
    $logDir = Split-Path -Parent $log
    $needsElevation = $false
    try {
        [IO.Directory]::CreateDirectory($logDir) | Out-Null
        $probe = Join-Path $logDir ('.uv3d-test-' + [guid]::NewGuid().ToString('N'))
        [IO.File]::WriteAllText($probe, '')
        [IO.File]::Delete($probe)
    } catch { $needsElevation = $true }
    $args = ('"{0}" --log "{1}" --launcher "{2}" --host "{3}"' -f
             $virtual,$log,$launcher,$hostExe)
    $verifiedRules = Join-Path $InstallFolder 'UV3DAddOn\config\simulated-controller-rules.json'
    if (Test-Path -LiteralPath $verifiedRules -PathType Leaf) {
        $args += (' --rules "{0}"' -f $verifiedRules)
    }
    if ($needsElevation) {
        Start-Process -FilePath $script:Python -ArgumentList $args -Verb RunAs -WindowStyle Hidden -ErrorAction Stop
    } else {
        Start-Process -FilePath $script:Python -ArgumentList $args -WorkingDirectory $InstallFolder -WindowStyle Hidden -ErrorAction Stop
    }
    $script:StatusLabel.Text = 'Loopback controller started (TCP/UDP 127.0.0.1:5001). Hardware replies not yet verified.'
}

function Start-NativePrintExp([string]$InstallFolder, [switch]$NoAddon) {
    if (-not (Test-VC2010X64Runtime $InstallFolder)) {
        $decision = [System.Windows.Forms.MessageBox]::Show(
            "PrintExp_X64.exe requires Visual C++ 2010 SP1 x64 (mfc100u.dll), which is missing." +
            [Environment]::NewLine +
            "Download and install this free Microsoft runtime now?",
            'PrintExp 3D: Required Microsoft Runtime', 'YesNo', 'Question')
        if ($decision -ne [System.Windows.Forms.DialogResult]::Yes) {
            throw 'Cannot start PrintExp until the 2010 x64 runtime is installed.'
        }
        Begin-Modification 'vc2010-install'
        return
    }
    $native = Join-Path $InstallFolder 'UV3DAddOn\dist\windows\PrintExp3DLauncher.exe'
    $hostExe = Join-Path $InstallFolder 'PrintExp_X64.exe'
    if ($NoAddon) {
        Start-Process -FilePath $hostExe -WorkingDirectory $InstallFolder -ErrorAction Stop
        $script:StatusLabel.Text = 'Launching original PrintExp without 3D (Shift+Launch).'
        return
    }
    if (-not (Test-Path -LiteralPath $native -PathType Leaf)) {
        throw 'The 3D launcher is missing; use Update from main.'
    }
    Start-Process -FilePath $native -ArgumentList ('"{0}"' -f $hostExe) -WorkingDirectory $InstallFolder -ErrorAction Stop
    $mode = Read-ProjectMode $InstallFolder
    $script:StatusLabel.Text = if ($mode -eq 1) {
        'Starting PrintExp in offline development mode.'
    } else {
        'Starting PrintExp using the normal online configuration.'
    }
}

$script:LaunchButton = New-Object System.Windows.Forms.Button
$script:LaunchButton.Text = 'Launch PrintExp + 3D'
$script:LaunchButton.Location = New-Object System.Drawing.Point(521,137)
$script:LaunchButton.Size = New-Object System.Drawing.Size(215,39)
$form.Controls.Add($script:LaunchButton)
$script:LaunchButton.Add_Click({
    try {
        if ($script:WorkerProcess) { return }
        $folder = Get-SelectedFolder
        $launcher = Join-Path $folder 'Start PrintExp with 3D.cmd'
        if (-not (Test-Path -LiteralPath $launcher)) { throw 'The 3D add-on is not installed. Click Install Add-on first.' }
        if ($script:SimulationCheck.Checked) {
            if (Test-SimulationProfile $folder) {
                Start-SimulatedPrintExp $folder
            } else {
                Begin-Modification 'simulate-enable'
            }
            return
        }
        if (Test-SimulationProfile $folder) {
            Begin-Modification 'simulate-disable'
            return
        }
        $mode = Read-ProjectMode $folder
        if ($mode -eq 0) {
            $decision = [System.Windows.Forms.MessageBox]::Show(
                'This PrintExp installation is configured for ONLINE operation.' +
                [Environment]::NewLine + [Environment]::NewLine +
                'Is this a development computer without the printer?' +
                [Environment]::NewLine +
                'YES: enable PrintExp debug mode (PROJECT_MODE=1) with a verified in-folder backup and UAC approval.' +
                [Environment]::NewLine +
                'NO: launch normally without changing settings.' +
                [Environment]::NewLine +
                'CANCEL: do not launch.',
                'PrintExp 3D: Offline Development', 'YesNoCancel', 'Question')
            if ($decision -eq [System.Windows.Forms.DialogResult]::Cancel) { return }
            if ($decision -eq [System.Windows.Forms.DialogResult]::Yes) {
                Begin-Modification 'offline-enable'
                return
            }
        }
        $baseline = (([System.Windows.Forms.Control]::ModifierKeys -band
                      [System.Windows.Forms.Keys]::Shift) -ne 0)
        Start-NativePrintExp $folder -NoAddon:$baseline
    } catch {
        $details = $_.Exception.Message
        if ($_.Exception -is [System.ComponentModel.Win32Exception] -and $_.Exception.NativeErrorCode -eq 5) {
            $details = 'Windows denied access to the add-on executable (error 5). This often means the previous installation retained the administrator temporary folder permissions. Use Update from main to repair the installed files. Original PrintExp files are unchanged.'
        }
        $script:StatusLabel.Text = $details
        [System.Windows.Forms.MessageBox]::Show($details, 'PrintExp 3D', 'OK', 'Error') | Out-Null
    }
})

$script:SimulationCheck = New-Object System.Windows.Forms.CheckBox
$script:SimulationCheck.Text = 'Simulate machine connection (offline test)'
$script:SimulationCheck.Location = New-Object System.Drawing.Point(20,191)
$script:SimulationCheck.Size = New-Object System.Drawing.Size(620,35)
$script:SimulationCheck.AutoSize = $false
$script:SimulationCheck.ForeColor = [System.Drawing.Color]::FromArgb(255,220,150)
$script:SimulationCheck.Checked = Test-SimulationProfile $script:FolderInput.Text
$form.Controls.Add($script:SimulationCheck)
$script:SimulationCheck.BringToFront()

$script:StatusLabel = New-Object System.Windows.Forms.Label
$script:StatusLabel.Text = 'Ready'
$script:StatusLabel.Location = New-Object System.Drawing.Point(20,242)
$script:StatusLabel.Size = New-Object System.Drawing.Size(700,55)
$script:StatusLabel.Anchor = 'Top,Left,Right'
$form.Controls.Add($script:StatusLabel)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 400
$timer.Add_Tick({
    if (-not $script:WorkerProcess) { return }
    $script:WorkerProcess.Refresh()
    if ($script:WorkerProcess.HasExited) { Finish-Modification; return }
    try {
        if (Test-Path -LiteralPath $script:WorkerLog) {
            $last = Get-Content -LiteralPath $script:WorkerLog -Tail 1 -ErrorAction Stop
            if ($last) { $script:StatusLabel.Text = [string]$last }
        }
    } catch { }
})
$timer.Start()
$form.Add_FormClosing({
    if ($script:WorkerProcess -and -not $script:WorkerProcess.HasExited) {
        $_.Cancel = $true
        $script:StatusLabel.Text = 'An installation operation is running. Close the manager once it finishes.'
        return
    }
    Save-Selection $script:FolderInput.Text
})
[void]$form.ShowDialog()
