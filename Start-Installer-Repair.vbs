Option Explicit
' One-time repair entrypoint: always use the Bootstrap-Installer.ps1 located
' beside THIS file. Unlike Start-Installer.vbs it never redirects to the
' outdated installed manager. The regular single-window UI is unchanged.
Dim shell, fso, folder, parent, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
If Not fso.FileExists(fso.BuildPath(folder, "Bootstrap-Installer.ps1")) Then
    MsgBox "Bootstrap-Installer.ps1 is missing. Extract the complete latest repository ZIP.", vbCritical, "PrintExp 3D"
    WScript.Quit 1
End If
parent = fso.GetParentFolderName(folder)
If Len(parent) = 0 Or Not fso.FolderExists(parent) Then
    parent = shell.ExpandEnvironmentStrings("%TEMP%")
End If
shell.CurrentDirectory = parent
cmd = "powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & fso.BuildPath(folder, "Bootstrap-Installer.ps1") & """"
shell.Run cmd, 0, False
