' SlackOff - launch without a console window
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root

If fso.FileExists(root & "\.venv\Scripts\pythonw.exe") Then
    shell.Run """" & root & "\.venv\Scripts\pythonw.exe"" """ & root & "\main.py""", 0, False
Else
    shell.Run "pythonw.exe """ & root & "\main.py""", 0, False
End If
