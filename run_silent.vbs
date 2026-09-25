Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "python" & chr(34) & " app.py", 0
Set WshShell = Nothing
