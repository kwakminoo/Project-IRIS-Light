@echo off
setlocal
cd /d "%~dp0\.."

if not exist ".venv-voice" (
  py -3 -m venv .venv-voice
)
".venv-voice\Scripts\python.exe" -m pip install --upgrade pip
".venv-voice\Scripts\pip.exe" install -r "services\voice_runtime\requirements-voice-mock.txt"
".venv-voice\Scripts\pip.exe" install -r "services\voice_runtime\requirements-voice.txt"

if /I "%~1"=="-Full" (
  echo Installing full voice models ^(torch, qwen-tts^)...
  ".venv-voice\Scripts\pip.exe" install torch qwen-tts
)

echo voice runtime ready: .venv-voice\Scripts\python.exe
echo mock default: VOICE_RUNTIME_MOCK=1
echo bind: 127.0.0.1:18765 only
endlocal
