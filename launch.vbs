Dim WshShell
Set WshShell = CreateObject("WScript.Shell")

Dim streamlitPath
streamlitPath = "C:\Users\ipascotto\AppData\Local\Python\pythoncore-3.14-64\Scripts\streamlit.exe"

Dim appPath
appPath = "U:\APP\chatbotAPI.py"

Dim cmd
cmd = """" & streamlitPath & """ run """ & appPath & """"

WshShell.Run cmd, 1, False

WScript.Sleep 6000
WshShell.Run "http://localhost:8501"
