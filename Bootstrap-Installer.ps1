#requires -Version 5.1
<#
.Purpose
  First-run bootstrap for the PrintExp 3D add-on. Uses Windows' built-in PowerShell
  and Windows Forms; Python and Git are *not* needed to open this screen.
  No vendor files are modified here.
#>
[CmdletBinding()]
param([switch]$CheckOnly)

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
    $location = $script:BuildToolsPath.Text.Trim()
    if ($location) {
        # Start-Process joins the argument array; quote paths containing spaces explicitly.
        $arguments += @('--installPath', ('"' + $location + '"'))
    }
    [void](Invoke-CheckedProcess -File $download -ProcessArguments $arguments -Name 'Visual Studio C++ Build Tools')
}

if ($CheckOnly) {
    Refresh-Status
    Write-Output "Python=$([bool]$script:Python)"
    Write-Output "Git=$([bool]$script:Git)"
    Write-Output "MSVC=$([bool]$script:Compiler)"
    Write-Output "Prebuilt=$([bool](Prebuilt-NativeFilesExist))"
    exit 0
}

if (-not [Environment]::Is64BitOperatingSystem) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show('This add-on requires 64-bit Windows.', 'PrintExp 3D') | Out-Null
    exit 1
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
Refresh-Status

$form = New-Object System.Windows.Forms.Form
$form.Text = 'PrintExp 3D Add-on - Dependency Setup'
$form.Size = New-Object System.Drawing.Size(680, 645)
$form.MinimumSize = New-Object System.Drawing.Size(680, 645)
$form.StartPosition = 'CenterScreen'
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$script:Form = $form

$title = New-Object System.Windows.Forms.Label
$title.Text = 'Prepare the PrintExp 3D Installer'
$title.Font = New-Object System.Drawing.Font('Segoe UI Semibold', 16)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(18, 16)
$form.Controls.Add($title)

$intro = New-Object System.Windows.Forms.Label
$intro.Text = 'Missing tools are downloaded from official sources. Already installed tools are reused.'
$intro.Size = New-Object System.Drawing.Size(635, 43)
$intro.Location = New-Object System.Drawing.Point(20, 55)
$form.Controls.Add($intro)

$script:StatusLabel = New-Object System.Windows.Forms.Label
$script:StatusLabel.Location = New-Object System.Drawing.Point(20, 101)
$script:StatusLabel.Size = New-Object System.Drawing.Size(635, 82)
$form.Controls.Add($script:StatusLabel)

$script:BuildToolsCheckbox = New-Object System.Windows.Forms.CheckBox
$script:BuildToolsCheckbox.Location = New-Object System.Drawing.Point(20, 190)
$script:BuildToolsCheckbox.Size = New-Object System.Drawing.Size(635, 50)
$script:BuildToolsCheckbox.Text = 'Install Microsoft C++ Build Tools if needed (large download; may require administrator approval)'
$form.Controls.Add($script:BuildToolsCheckbox)

$pathLabel = New-Object System.Windows.Forms.Label
$pathLabel.Text = 'Build Tools install location (other tools use their standard paths):'
$pathLabel.Location = New-Object System.Drawing.Point(20, 238)
$pathLabel.Size = New-Object System.Drawing.Size(635, 24)
$form.Controls.Add($pathLabel)
$script:BuildToolsPath = New-Object System.Windows.Forms.TextBox
$script:BuildToolsPath.Location = New-Object System.Drawing.Point(20, 263)
$script:BuildToolsPath.Size = New-Object System.Drawing.Size(620, 25)
$script:BuildToolsPath.Anchor = 'Top,Left,Right'
$script:BuildToolsPath.Text = if (Test-Path -LiteralPath 'X:\') { 'X:\VisualStudioBuildTools' } else { '' }
$form.Controls.Add($script:BuildToolsPath)

$script:LogBox = New-Object System.Windows.Forms.TextBox
$script:LogBox.Multiline = $true
$script:LogBox.ReadOnly = $true
$script:LogBox.ScrollBars = 'Vertical'
$script:LogBox.Font = New-Object System.Drawing.Font('Consolas', 9)
$script:LogBox.Location = New-Object System.Drawing.Point(20, 302)
$script:LogBox.Size = New-Object System.Drawing.Size(620, 151)
$script:LogBox.Anchor = 'Top,Bottom,Left,Right'
$form.Controls.Add($script:LogBox)

$folderLabel = New-Object System.Windows.Forms.Label
$folderLabel.Text = 'PrintExp installation folder (remembered automatically):'
$folderLabel.Location = New-Object System.Drawing.Point(20, 466)
$folderLabel.Size = New-Object System.Drawing.Size(635, 24)
$form.Controls.Add($folderLabel)

$script:PrintExpPath = New-Object System.Windows.Forms.TextBox
$script:PrintExpPath.Location = New-Object System.Drawing.Point(20, 494)
$script:PrintExpPath.Size = New-Object System.Drawing.Size(525, 27)
$script:PrintExpPath.Anchor = 'Bottom,Left,Right'
$form.Controls.Add($script:PrintExpPath)

$browse = New-Object System.Windows.Forms.Button
$browse.Text = 'Browse...'
$browse.Location = New-Object System.Drawing.Point(552, 494)
$browse.Size = New-Object System.Drawing.Size(88, 30)
$browse.Anchor = 'Bottom,Right'
$browse.Add_Click({
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Select the folder containing PrintExp_X64.exe'
    $candidate = $script:PrintExpPath.Text.Trim()
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { $dialog.SelectedPath = $candidate }
    if ($dialog.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) {
        $script:PrintExpPath.Text = $dialog.SelectedPath
        Save-PrintExpSelection $dialog.SelectedPath
    }
    $dialog.Dispose()
})
$form.Controls.Add($browse)

$script:PrintExpPath.Add_Leave({
    $selected = $script:PrintExpPath.Text.Trim()
    if ($selected -and (Test-Path -LiteralPath (Join-Path $selected 'PrintExp_X64.exe'))) {
        Save-PrintExpSelection $selected
    }
})
$form.Add_FormClosing({
    $selected = $script:PrintExpPath.Text.Trim()
    if ($selected -and (Test-Path -LiteralPath (Join-Path $selected 'PrintExp_X64.exe'))) {
        Save-PrintExpSelection $selected
    }
})

$script:UpdateButton = New-Object System.Windows.Forms.Button
$script:UpdateButton.Text = 'Update from main'
$script:UpdateButton.Location = New-Object System.Drawing.Point(136, 551)
$script:UpdateButton.Size = New-Object System.Drawing.Size(170, 38)
$script:UpdateButton.Anchor = 'Bottom,Left'
$form.Controls.Add($script:UpdateButton)

$script:ContinueButton = New-Object System.Windows.Forms.Button
$script:ContinueButton.Text = 'Install missing dependencies and open installer'
$script:ContinueButton.Location = New-Object System.Drawing.Point(310, 551)
$script:ContinueButton.Size = New-Object System.Drawing.Size(330, 38)
$script:ContinueButton.Anchor = 'Bottom,Right'
$form.Controls.Add($script:ContinueButton)

$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Cancel'
$cancel.Location = New-Object System.Drawing.Point(20, 551)
$cancel.Size = New-Object System.Drawing.Size(105, 37)
$cancel.Anchor = 'Bottom,Left'
$cancel.Add_Click({ $form.Close() })
$form.Controls.Add($cancel)

function Ensure-PythonAndGit {
    if (-not $script:Python) {
        if (Install-UsingWinget 'Python.Python.3.13') { Refresh-Status }
        if (-not $script:Python) {
            Log-Message 'Using the official Python.org installer as a fallback.'
            Install-PythonFallback
            Refresh-Status
        }
        if (-not $script:Python) { throw 'Python was installed but cannot be found with Tkinter. Restart Windows and retry.' }
        Log-Message "Python ready: $script:Python"
    }
    if (-not $script:Git) {
        if (Install-UsingWinget 'Git.Git') { Refresh-Status }
        if (-not $script:Git) {
            Log-Message 'Using the official signed Git for Windows installer as a fallback.'
            Install-GitFallback
            Refresh-Status
        }
        if (-not $script:Git) { throw 'Git was installed but cannot be found. Restart Windows and retry.' }
        Log-Message "Git ready: $script:Git"
    }
    $env:Path = "$(Split-Path -Parent $script:Git);$env:Path"
}

function Save-PrintExpSelection([string]$SelectedFolder) {
    $parent = Split-Path -Parent $script:SelectionFile
    if (-not (Test-Path -LiteralPath $parent)) { [void](New-Item -ItemType Directory -Path $parent -Force) }
    [IO.File]::WriteAllText($script:SelectionFile, $SelectedFolder, [Text.Encoding]::UTF8)
}

function Test-UpdateNeedsAdmin([string]$InstallFolder) {
    $managedFolder = Join-Path $InstallFolder 'UV3DAddOn'
    $probe = Join-Path $managedFolder ('.uv3d-write-probe-' + [Guid]::NewGuid().ToString('N'))
    $file = $null
    try {
        $file = [IO.File]::Open($probe, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        return $false
    } catch [System.UnauthorizedAccessException] {
        return $true
    } catch [System.IO.IOException] {
        if ($_.Exception.HResult -eq -2147024891) { return $true }
        throw
    } finally {
        if ($file) { $file.Dispose(); [IO.File]::Delete($probe) }
    }
}

function Invoke-UpdateFromMain {
    $folder = $script:PrintExpPath.Text.Trim()
    if (-not $folder -or -not (Test-Path -LiteralPath (Join-Path $folder 'PrintExp_X64.exe'))) {
        throw 'Select the folder containing PrintExp_X64.exe before updating.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $folder 'UV3DAddOn\.uv3d-managed-install.json'))) {
        throw 'The 3D add-on is not installed yet. Use Open Installer and Install first.'
    }
    if ([System.Windows.Forms.MessageBox]::Show(
        'Update the installed 3D add-on from the latest main branch? Close PrintExp first. Original PrintExp files remain unchanged.',
        'Update from main', [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question) -ne [System.Windows.Forms.DialogResult]::Yes) { return }
    Save-PrintExpSelection $folder
    Ensure-PythonAndGit
    $scriptPath = Join-Path $script:Root 'update_addon.py'
    if (-not (Test-Path -LiteralPath $scriptPath)) { throw 'Missing update_addon.py. Download the latest installer.' }
    $logPath = Join-Path $env:TEMP ('uv3d-update-' + [Guid]::NewGuid().ToString('N') + '.log')
    $arguments = ('"' + $scriptPath + '" --target "' + $folder + '" --log-file "' + $logPath + '"')
    $options = @{ FilePath=$script:Python; ArgumentList=$arguments; WorkingDirectory=$script:Root; PassThru=$true }
    if (Test-UpdateNeedsAdmin $folder) {
        Log-Message 'Windows administrator permission is needed for the PrintExp folder.'
        $options['Verb'] = 'RunAs'
    }
    Log-Message 'Updating installed add-on from origin/main...'
    $process = Start-Process @options
    while (-not $process.HasExited) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 300
        $process.Refresh()
    }
    if (Test-Path -LiteralPath $logPath) {
        foreach ($line in (Get-Content -LiteralPath $logPath -ErrorAction SilentlyContinue)) { Log-Message $line }
        Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue
    }
    if ($process.ExitCode -ne 0) { throw "Update failed (code $($process.ExitCode)). See log above." }
    Log-Message 'Update complete. Original PrintExp files remain unchanged.'
}

function Update-Display {
    $prebuilt = Prebuilt-NativeFilesExist
    $compilerReq = -not $prebuilt
    $pyText = if ($script:Python) {'Installed'} else {'Missing'}
    $gitText = if ($script:Git) {'Installed'} else {'Missing'}
    $compilerText = if ($script:Compiler) {'Installed'} elseif ($prebuilt) {'Not needed (prebuilt x64 files exist)'} else {'Missing'}
    $script:StatusLabel.Text = "Python 3 + Tkinter: $pyText`r`nGit for Windows: $gitText`r`nMicrosoft C++ Build Tools: $compilerText"
    $script:BuildToolsCheckbox.Enabled = $compilerReq -and -not $script:Compiler
    $script:BuildToolsCheckbox.Checked = $script:BuildToolsCheckbox.Enabled
    $script:BuildToolsPath.Enabled = $script:BuildToolsCheckbox.Enabled
    if ($script:Python -and $script:Git -and ($script:Compiler -or $prebuilt)) {
        $script:ContinueButton.Text = 'Open Installer'
    } else {
        $script:ContinueButton.Text = 'Install missing tools and open installer'
    }
}


# Restore the folder last selected in either window.
if (Test-Path -LiteralPath $script:SelectionFile) {
    try { $script:PrintExpPath.Text = [IO.File]::ReadAllText($script:SelectionFile, [Text.Encoding]::UTF8).Trim() } catch { }
}
Update-Display
Log-Message 'Update from main is available here. Install/Uninstall are in the next window.'

$script:UpdateButton.Add_Click({
    $script:UpdateButton.Enabled = $false
    $script:ContinueButton.Enabled = $false
    try { Invoke-UpdateFromMain }
    catch {
        Log-Message "ERROR: $($_.Exception.Message)"
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'PrintExp update',
            [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    } finally {
        $script:UpdateButton.Enabled = $true
        $script:ContinueButton.Enabled = $true
        Refresh-Status
        Update-Display
    }
})

$script:ContinueButton.Add_Click({
    $script:ContinueButton.Enabled = $false
    $script:UpdateButton.Enabled = $false
    $script:BuildToolsCheckbox.Enabled = $false
    $script:BuildToolsPath.Enabled = $false
    try {
        Ensure-PythonAndGit
        if (-not $script:Compiler -and -not (Prebuilt-NativeFilesExist)) {
            if ($script:BuildToolsCheckbox.Checked) {
                Install-Compiler
                Refresh-Status
                if (-not $script:Compiler) {
                    throw 'C++ Build Tools installed but compiler not detected. Restart Windows and retry.'
                }
                Log-Message 'Microsoft C++ compiler ready.'
            } else {
                throw 'Native 3D page binaries are not included. Enable C++ Build Tools or use prebuilt binaries.'
            }
        }
        $selected = $script:PrintExpPath.Text.Trim()
        if ($selected -and (Test-Path -LiteralPath (Join-Path $selected 'PrintExp_X64.exe'))) {
            Save-PrintExpSelection $selected
        }
        Log-Message 'Dependencies ready. Opening the graphical PrintExp add-on installer...'
        $form.Hide()
        & $script:Python (Join-Path $script:Root 'installer.py') --target $selected
        if ($LASTEXITCODE -ne 0) { throw "The installer exited with code $LASTEXITCODE." }
        $form.Close()
    } catch {
        $form.Show()
        Log-Message "ERROR: $($_.Exception.Message)"
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'PrintExp dependency setup',
            [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
        $script:ContinueButton.Enabled = $true
        $script:UpdateButton.Enabled = $true
        Refresh-Status
        Update-Display
    }
})
[void]$form.ShowDialog()
