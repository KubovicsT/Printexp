Option Explicit

' The bootstrap can be unpacked anywhere. Once an add-on is installed, always
' start its own current manager, not the stale version in an old ZIP download.
' We use only the folder the user saved, never scan other PrintExp installations.
Dim shell, fso, root, command, preference, reader, selected, managed
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)

preference = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\PrintExp3DAddOn\selected-install.txt"
If fso.FileExists(preference) Then
    On Error Resume Next
    ' PowerShell saves this selection as UTF-8 without BOM, not UTF-16.
    ' ADODB.Stream reads the same encoding, including non-ASCII folder names.
    Set reader = CreateObject("ADODB.Stream")
    reader.Type = 2
    reader.Charset = "utf-8"
    reader.Open
    reader.LoadFromFile preference
    If Err.Number = 0 Then
        selected = Trim(reader.ReadText)
    Else
        Err.Clear
    End If
    reader.Close
    On Error GoTo 0
    If Len(selected) > 0 Then
        managed = fso.BuildPath(selected, "UV3DAddOn")
        If fso.FileExists(fso.BuildPath(managed, ".uv3d-managed-install.json")) And _
           fso.FileExists(fso.BuildPath(managed, "Bootstrap-Installer.ps1")) And _
           fso.FileExists(fso.BuildPath(selected, "PrintExp_X64.exe")) Then
            root = managed
        End If
    End If
End If

command = "powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & root & "\Bootstrap-Installer.ps1"""
shell.Run command, 0, False
