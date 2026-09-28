@echo off
net use U: \\serveur-prod\utilisateurs\ipo /persistent:no 2>nul
cd /d U:\APP
C:\Users\ipascotto\AppData\Local\Python\pythoncore-3.14-64\Scripts\streamlit.exe run chatbotAPI.py
