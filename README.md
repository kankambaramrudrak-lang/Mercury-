# Mercury

**Mercury is an experimental, local-first Windows voice assistant.** It listens for speech, recognizes it on-device, routes a small set of commands to guarded tools, and speaks and prints its replies. Optional modules can use a local Ollama model, search a user-selected folder, or connect to Gmail, Google Calendar, WhatsApp Business, and Twilio when the owner configures those services.

Mercury is a personal software project, not a finished product. Voice accuracy and the integrations have not been validated across different computers or accounts. The default configuration keeps external account integrations and the local LLM disabled. Review the limitations and privacy notes before enabling tools.

## What it can do

- Listen continuously while voice mode is running; speech is segmented after a pause. Press **Esc** to exit.
- Recognize English speech locally with Vosk, or optionally faster-whisper.
- Speak replies with the Windows SAPI voice and print the same reply in the terminal.
- Add, list, count, complete, update, and button-confirm deletion of local tasks.
- Set local timers and relative reminders; open allowlisted apps/sites; create folders within a workspace; and search the web by opening a browser results page.
- Search supported files in a configured workspace and answer questions using an optional local Ollama model.
- Optionally read Gmail and the primary Google Calendar, create/send Gmail messages after button approval, reply to eligible WhatsApp messages after approval, and place or schedule Twilio calls after approval.
- Optionally create an approved project specification and ask the locally configured Codex CLI/Ollama setup to generate a first version in a new workspace folder.

These are narrow, explicitly implemented actions. Mercury is not a general computer-control agent: it cannot do arbitrary things, click around websites, or safely infer every command. **It does not automate websites or run arbitrary shell commands from the LLM.**

## Quick start

### Requirements

- Windows 10 or 11
- Python 3.11
- A microphone, speakers or headphones, and a Windows SAPI voice for voice mode
- Internet for initial Python package and Vosk model downloads

### Install

Open PowerShell in the repository folder:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
New-Item -ItemType Directory -Force model | Out-Null
Invoke-WebRequest -Uri https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -OutFile model\vosk-model.zip
Expand-Archive -Path model\vosk-model.zip -DestinationPath model -Force
Remove-Item model\vosk-model.zip
```

The extracted Vosk folder should be `model\vosk-model-small-en-us-0.15`. The model is downloaded separately and is not included in Git. Its published license and memory requirements are listed on [Vosk's model page](https://alphacephei.com/vosk/models).

### Run

```powershell
python main.py
```

Wait for the ready message, say a command, then pause. The microphone remains open while voice mode runs. `Esc` exits. For typing instead of microphone input, run `python main.py --text`. To check the speaker separately, use `python main.py --test-speech`; to list available audio devices, use `python main.py --list-devices`. Run `python main.py --doctor` for read-only setup diagnostics.

The starter settings are in [`settings.toml`](settings.toml). They use the Windows default microphone and leave Ollama, Google, WhatsApp, and Twilio disabled. See the [User Guide](docs/USER_GUIDE.md) before changing settings or connecting accounts.

## User documentation

- [User Guide](docs/USER_GUIDE.md) — setup, configuration, commands, integrations, privacy, troubleshooting, and limitations.
- [Architecture](docs/ARCHITECTURE.md) — how audio, routing, tools, approvals, and storage fit together.
- [Security notes](SECURITY.md) — local data and reporting a security issue.

## Development checks

```powershell
python -m unittest discover -s tests -v
python -m compileall -q main.py accuracy audio core tools tests
```

The tests use fake service clients, fake audio/speech components, and temporary storage. They do not prove that a real microphone, speaker, OAuth account, WhatsApp webhook, Twilio number, or local model works on your computer. No live account actions should be used as test cases.

## License

Mercury's project code is released under the [MIT License](LICENSE). Downloaded models and installed dependencies retain their own licenses and terms. See [Third-party software and models](docs/USER_GUIDE.md#third-party-software-and-models).

## Project status

This project is experimental and provided without warranty. Do not rely on it for emergencies, safety-critical tasks, or unattended communications. Review every approval prompt and verify external actions in the relevant provider account.
