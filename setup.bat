@echo off
rem MorasFlow.si setup. Safe to run again (e.g. after changing the logo in voiceflow\config.local.yaml).
cd /d "%~dp0"

set PY=
for %%v in (3.12 3.13 3.14) do if not defined PY py -%%v -c "" 2>nul && set PY=%%v
if not defined PY (
    echo Python 3.12, 3.13 or 3.14 is needed. Install it from https://www.python.org/downloads/
    echo ^(it includes the "py" launcher this uses^), then run setup.bat again.
    goto :failed
)

rem An environment made by an older setup (Python 3.11 can't install the packages) or with a Python that has
rem since been uninstalled won't work: start it afresh.
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python -c "import sys; sys.exit(sys.version_info < (3, 12))" 2>nul || (
        echo Rebuilding the Python environment ^(made with an unsupported or missing Python^)...
        rmdir /s /q .venv
    )
)
if not exist .venv\Scripts\python.exe (
    echo Creating the Python environment with Python %PY%...
    py -%PY% -m venv .venv || goto :failed
)
echo Installing packages, then the offline speech model (first time: a few minutes and about 0.5 GB)...
.venv\Scripts\python -m pip install --disable-pip-version-check -q -r voiceflow\requirements.txt || goto :failed

if not exist voiceflow\vocab.txt copy voiceflow\vocab.example.txt voiceflow\vocab.txt >nul
set NEW_ENV=
if not exist voiceflow\.env (copy voiceflow\.env.example voiceflow\.env >nul & set NEW_ENV=1)

.venv\Scripts\python voiceflow\install.py || goto :failed

echo.
echo Setup complete. Start MorasFlow.si from the Desktop or Start menu, then hold Ctrl+Win and speak.
if defined NEW_ENV (
    echo.
    echo Last step: paste your free Groq API key ^(console.groq.com, API Keys^) after GROQ_API_KEY= in the
    echo file that is opening now, then save it. Without a key it still works, just slower and without cleanup.
    notepad voiceflow\.env
)
pause
exit /b 0

:failed
echo.
echo Setup did not finish; see the message above.
pause
exit /b 1
