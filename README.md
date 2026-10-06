# Hercules Milestone 1: local voice greeting

A small Windows proof of concept: hold **Right Ctrl**, say a greeting, release the key, and Hercules speaks a reply. It does not connect to an LLM, cloud speech service, or account. Audio is processed locally and the recognized words are not printed or saved.

## Requirements

- Windows 10 or 11
- Python 3.11 (use `python`, not `py`, if the Python launcher selects a different version)
- A working microphone and an installed Windows SAPI speech voice
- Internet for the one-time Python package and speech model downloads; after setup, recognition and speech output work offline

## Setup (PowerShell, from this folder)

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Download the approximately 40 MB Vosk small US English model and unpack it into `model\vosk-model-small-en-us-0.15`:

```powershell
New-Item -ItemType Directory -Force model | Out-Null
Invoke-WebRequest -Uri https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -OutFile model\vosk-model.zip
Expand-Archive -Path model\vosk-model.zip -DestinationPath model -Force
Remove-Item model\vosk-model.zip
```

The model is excluded from Git by `.gitignore`. Vosk publishes this small model under Apache 2.0; it uses about 300 MB of memory while running. [Vosk's model list](https://alphacephei.com/vosk/models) documents model sizes and licenses.

## Run

```powershell
python main.py
```

Wait for “Hercules is ready,” hold **Right Ctrl**, say “hello” (or “hi” / “hey”), and release the key. Press **Esc** to quit. `python main.py --list-devices` lists audio devices if the default microphone is unavailable.

## Checks

```powershell
python -m unittest discover -s tests -v
python -m compileall -q main.py tests
```

If PowerShell blocks virtual-environment activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that PowerShell window, then activate `.venv` again. Windows privacy settings must allow microphone access to desktop apps. Recognition quality depends on microphone, room noise, accent, and the small US English model. The prototype listens only while Right Ctrl is held; `pynput` needs to receive global keyboard events, which managed-device policies may restrict.

## Milestone 2A: local tasks

The voice commands are:

- **Add task** followed by a description, for example “Add task buy milk”
- **List tasks** to hear open tasks and their numbers
- **Complete task** followed by one task number, for example “Complete task one”
- **Update task** followed by its number, “to”, and a new description
- **Delete task** followed by its number; Hercules reads the task and waits for the exact phrase **Confirm delete task** followed by the same number. A bare “yes” cancels the pending deletion.

Task data is stored locally in `data\hercules.sqlite3` and persists between runs. The `data\` directory is ignored by Git. Hercules does not log the full recognized utterance or store audio. Spoken and printed replies can include task descriptions when needed to report or confirm a task. If a task number is unclear, it asks you to repeat it instead of selecting a task. Tests use temporary database files and do not access the local task database.

Hercules prints each spoken response in the terminal immediately before speaking it. If a delete confirmation is unclear or uses another number, Hercules cancels the deletion and leaves the task unchanged.

Run the focused tests with:

```powershell
python -m unittest discover -s tests -v
```

## Voice diagnostics

Run `python main.py --test-speech` to speak one fixed sentence through the Windows speech engine without opening the microphone. This checks speaker output separately from recognition.

Run `python main.py --debug-recognition` to use push-to-talk with recognized words displayed in the terminal. This mode exposes your speech locally while it is running; the words are not written to a file or database. Normal runs keep recognized words hidden.
