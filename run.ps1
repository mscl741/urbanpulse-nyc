# Run UrbanPulse with the project virtualenv (avoids "wrong Python" issues)
Set-Location $PSScriptRoot
& .\.venv\Scripts\python.exe -m streamlit run src\app.py
