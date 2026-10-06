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
python -m compileall -q main.py audio core tools tests
```

If PowerShell blocks virtual-environment activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that PowerShell window, then activate `.venv` again. Windows privacy settings must allow microphone access to desktop apps. Recognition quality depends on microphone, room noise, accent, and the small US English model. The prototype listens only while Right Ctrl is held; `pynput` needs to receive global keyboard events, which managed-device policies may restrict.

## Milestone 2A: local tasks

The voice commands are:

- **Add task** followed by a description, for example “Add task buy milk”
- **List tasks** to hear open tasks and their numbers
- **Complete task** followed by one task number, for example “Complete task one”
- **Update task** followed by its number, “to”, and a new description
- **Delete task** is currently refused without changing the task. Button confirmation is planned for Phase 3.

Task data is stored locally in `data\hercules.sqlite3` and persists between runs. The `data\` directory is ignored by Git. Hercules does not log the full recognized utterance or store audio. Spoken and printed replies can include task descriptions when needed to report or confirm a task. If a task number is unclear, it asks you to repeat it instead of selecting a task. Tests use temporary database files and do not access the local task database.

Hercules prints each spoken response in the terminal immediately before speaking it.

Run the focused tests with:

```powershell
python -m unittest discover -s tests -v
```

## Voice diagnostics

Run `python main.py --test-speech` to speak one fixed sentence through the Windows speech engine without opening the microphone. This checks speaker output separately from recognition.

Recognized speech is never displayed or saved. The former `--debug-recognition` option has been removed to preserve this privacy rule.

To use Hercules without a microphone, run `python main.py --text`. Type a command and press Enter; type `exit` or `quit` to leave text mode.

## Project layout

- `audio/` captures push-to-talk audio, recognizes speech locally, and speaks assistant replies.
- `core/router.py` routes both typed and recognized text through `CommandRouter.handle()`.
- `tools/tasks.py` contains the local SQLite task operations. Deletion is refused until a button confirmation exists.
- `main.py` starts the app and selects voice, text, device-list, or speech-test mode.
