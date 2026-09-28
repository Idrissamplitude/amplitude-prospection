import subprocess
import webbrowser
import time
import sys
import os

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

streamlit = r"C:\Users\ipascotto\AppData\Local\Python\pythoncore-3.14-64\Scripts\streamlit.exe"
app = r"U:\APP\chatbotAPI.py"

print(f"streamlit exists: {os.path.exists(streamlit)}", flush=True)
print(f"app exists: {os.path.exists(app)}", flush=True)

try:
    proc = subprocess.Popen(
        [streamlit, "run", app],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        cwd=r"U:\APP",
        stdout=open(r"U:\APP\streamlit_new.log", "w"),
        stderr=subprocess.STDOUT,
    )
    print(f"Process started PID={proc.pid}", flush=True)
except Exception as e:
    print(f"Error: {e}", flush=True)
    sys.exit(1)

time.sleep(6)
webbrowser.open("http://localhost:8501")
print("Browser opened", flush=True)
