# Mercury User Guide

This guide describes the current source tree. Optional integrations need separate accounts and setup. A feature being described here does not mean it has been tested against your particular device or provider account.

## 1. What Mercury is

Mercury is a Python desktop app for Windows. It combines a microphone listener, local speech recognition, a command router, registered tools, a confirmation window for higher-risk actions, and Windows speech output. In voice mode, it stays active and treats a pause as the end of a short utterance. It has no wake word and does not require push-to-talk. Text mode uses the same command router without recording audio.

Mercury can run without an LLM for its built-in commands. If enabled, Ollama provides local open-ended responses and can choose from Mercury's registered tool list. It cannot choose an unregistered tool or run a raw shell command. Known command parsing happens before the model fallback. Local file search runs only under the configured workspace.

## 2. System requirements

- Windows 10 or 11; other operating systems are not currently supported by the audio and credential-storage implementation.
- Python 3.11. Use `python` if the Windows `py` launcher selects a different version.
- A working microphone and a Windows SAPI voice for voice interaction.
- Internet access for installing Python dependencies and downloading the Vosk model. Faster-whisper downloads its model the first time it is selected. After setup, speech recognition and text-to-speech can run locally.
- Optional: Ollama and a downloaded model; a Google Cloud OAuth desktop client; Meta WhatsApp Business Platform access; and/or a Twilio account and enabled phone number, depending on the features you want.

Hardware performance varies. The `small.en` faster-whisper model uses CPU `int8` in this project; slower computers can have noticeable response delay. The `llama3.2:3b` Ollama model needs additional disk, memory, and CPU/GPU resources. Model tags and provider terms may change; check the official provider pages before setup.

## 3. Installation

In PowerShell, change to the folder containing `main.py`, then run:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, you can use the venv executable directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Download the small US English Vosk model, then extract it under `model`:

```powershell
New-Item -ItemType Directory -Force model | Out-Null
Invoke-WebRequest -Uri https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -OutFile model\vosk-model.zip
Expand-Archive -Path model\vosk-model.zip -DestinationPath model -Force
Remove-Item model\vosk-model.zip
```

The expected model path is `model\vosk-model-small-en-us-0.15`. The download is not part of the Git repository. Vosk identifies the small model's license and resource requirements on its [model list](https://alphacephei.com/vosk/models).

Check the local configuration and installed packages without activating microphone or account integrations:

```powershell
python main.py --doctor
```

The doctor command does not capture audio, play a sound, or read provider credentials. It contacts only the configured localhost Ollama endpoint when local AI is enabled.

## 4. Running Mercury

| Command | Purpose |
| --- | --- |
| `python main.py` | Start always-listening voice mode. Pause after speaking; press **Esc** to exit. |
| `python main.py --text` | Type commands into the terminal; type `exit` or `quit` to leave. Replies are also spoken. |
| `python main.py --test-speech` | Speak a fixed test sentence without opening the microphone. |
| `python main.py --list-devices` | List audio devices so you can choose a microphone. |
| `python main.py --doctor` | Run read-only local setup checks. |
| `python main.py --setup-whatsapp` | Securely enter Meta credentials into Windows Credential Manager. |
| `python main.py --setup-twilio` | Securely enter Twilio credentials into Windows Credential Manager. |
| `python -m accuracy.run` | Run the fixed 50-phrase speech benchmark. Read the warning in [Accuracy benchmark](#7-accuracy-benchmark) first. |

At startup Mercury prints and speaks its ready status. It prints each user-facing reply immediately before speaking it. Error/status messages and ready/listening indicators are printed; not every internal event is spoken. Recognized speech is never displayed as debug output.

## 5. Configuration

Edit `settings.toml` in a text editor, save it, then restart Mercury. Paths are relative to the settings file unless absolute. `workspace_folder` controls both file search and where folder/project tools may write; use a narrow folder that you are comfortable allowing Mercury to search. Do not point it at an entire drive unless you intend that.

### Speech recognition

Default:

```toml
microphone_device = "default"
speech_recognizer = "vosk"
speech_model_size = "small"
vosk_confidence_threshold = 0.65
faster_whisper_confidence_threshold = 0.45
```

`"default"` follows the Windows default recording device. Use `python main.py --list-devices` to see device IDs, then set `microphone_device` to a listed integer ID or exact device name if needed. A device ID can change after connecting or removing audio hardware.

To use faster-whisper instead, first install the optional backend if your installed requirements did not include it:

```powershell
python -m pip install "faster-whisper>=1.1,<2"
```

Then set:

```toml
speech_recognizer = "faster-whisper"
speech_model_size = "small.en"
```

The model download happens on first use. The prompt is built from `accuracy/commands.txt`. Both recognizers are English-focused. Confidence is a rough recognition score, not a guarantee that the transcript is correct. Low-confidence voice recognition is spoken back as a private “Did you say…?” question; say yes or no. Fuzzy matching is limited to known command phrases and does not intentionally rewrite task numbers or descriptions.

### Local AI and workspace access

Local AI is disabled by default:

```toml
local_ai_enabled = false
local_ai_model = "llama3.2:3b"
local_ai_url = "http://localhost:11434"
```

To enable it, install Ollama from its official site, download a compatible local model, then set `local_ai_enabled = true`. Mercury accepts only a localhost HTTP Ollama endpoint. The model can answer general questions and request registered tools; tool parameters are validated and confirm-risk tools remain approval-gated. Results depend on the model and can be incorrect. The project does not download or install Ollama for you.

When a query appears to concern workspace files, Mercury searches files first and provides a small set of excerpts to the local model. Search is bounded to supported text and office document formats, skips hidden and known sensitive/environment folders, limits scanned files and file size, and returns a few short excerpts. This is a convenience boundary, not a complete data-loss-prevention scanner. Keep secrets and sensitive records outside the workspace. Image-only scanned PDFs are not OCR'd.

### App allowlist and installs

Opening apps and web destinations is disabled until you add allowlisted entries. Example:

```toml
app_whitelist = [
  "ChatGPT=https://chatgpt.com",
  "Code=C:\\Program Files\\Microsoft VS Code\\Code.exe",
]
```

Web entries must use HTTPS. Executable entries must point to a direct `.exe` or `.com`; arbitrary command-line arguments are not accepted. Unknown aliases are refused. Opening a site only opens the browser; Mercury does not log in, read the page, or automate it. Web search opens a Google results page in the default browser, Chrome, Edge, or Firefox.

Package installation is disabled by default. To enable a package, add its exact reviewed `winget` package ID to `install_whitelist`; Mercury shows the exact command in a confirmation dialog before running it. Availability and UAC behavior depend on Windows and the package.

## 6. Built-in commands and integrations

The command parser accepts a constrained set of phrases. Examples are guides, not guaranteed speech transcripts. Text mode can help determine whether a problem is speech recognition or command routing.

### Tasks

- “Add task buy milk”
- “List tasks”
- “Count tasks”
- “Complete task one”
- “Update task one to buy oat milk”
- “Delete task one” — displays the task and requires an explicit **Approve** click. Cancel is the safe default; a missing dialog or timeout refuses the action.

Task data is stored in the local SQLite database under `data/` and persists across runs. The current source retains a legacy internal filename `hercules.sqlite3`; it is not a product name or a cloud service.

### Reminders and timers

- “Remind me in 10 minutes to call Sam”
- “Set a timer for 5 minutes”

Relative delays support seconds, minutes, and hours. Mercury must remain running to deliver the alert. The app stores reminder text in local SQLite; the database is not encrypted. A Windows toast notification is not implemented. Calendar-time reminders are not supported.

### Desktop and workspace

- “Open ChatGPT” — only works if `ChatGPT` is in `app_whitelist`.
- “Create a folder called project notes” — creates a folder only inside the configured workspace.
- “Search the web for local speech recognition in Edge” — opens results; it does not read the page.
- With local AI enabled: ask a question about workspace text files. Supported formats include common source/text formats and PDF, DOCX, PPTX, XLSX. Search is read-only; Mercury does not offer general edits to existing files.
- “Start project for a recipe tracker” — begins a short questionnaire. Mercury displays a generated `SPEC.md` and asks for approval before creating the folder. If approved, it can invoke the Codex CLI with local Ollama in a workspace-write sandbox. Review the generated diff and approve its checkpoint. This depends on Codex CLI being installed and configured. It is an experimental workflow, not an autonomous long-running developer.

### Gmail and Google Calendar (optional)

The Google integration uses official Gmail and Calendar APIs. It can search Gmail metadata/snippets, read upcoming events on the primary calendar, create a Gmail draft, and send email. Drafting and sending require a button approval showing the exact recipient, subject, and body. Email content and search queries are sent to Google when you use the integration.

Setup overview:

1. In Google Cloud, create a project and enable the Gmail API and Google Calendar API.
2. Configure an OAuth consent screen as appropriate for your account and create an OAuth client of type **Desktop app**.
3. Save its client JSON at the path set by `google_credentials_file` (the default is the ignored `secrets/google-oauth-client.json`). Never commit this file.
4. Set `google_enabled = true` in `settings.toml`, restart Mercury, and use a Google feature. The official OAuth flow opens for consent.

Use Google's official [Calendar Python quickstart](https://developers.google.com/workspace/calendar/api/quickstart/python), [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes), and [Gmail send guide](https://developers.google.com/workspace/gmail/api/guides/sending) for current steps and consent requirements. Gmail read/compose scopes can require OAuth verification for distributed applications; requirements depend on the selected scopes and account. This project does not provide a shared OAuth client or claim Google verification. OAuth refresh credentials are stored in Windows Credential Manager. The integration is off by default; no user account is bundled.

### WhatsApp Business and Twilio calls (optional, may cost money)

WhatsApp requires a Meta WhatsApp Business Platform setup, an enabled sender, access token, opted-in contact, and compliance with Meta's messaging rules. The current inbox only keeps up to 50 incoming text messages in memory during the running session. Replies are possible only to an eligible recent inbound message and need button approval. To receive webhooks while running locally, the app binds to `127.0.0.1`; Meta requires a public HTTPS callback, so you must independently arrange and secure a forwarding endpoint/tunnel. Mercury does not provide hosting. The webhook checks Meta's signature. Messages received while Mercury is closed are not backfilled.

Twilio calls require an enabled Twilio Voice account/number, an opted-in contact, and available balance/region support. Calls are limited and not recorded by the code; the configured announcement is read aloud. Calls require button approval and may incur provider charges. Scheduled calls also require approval when scheduled; Mercury must be running and connected at the due time, and the app makes one attempt without automatic retry.

Store contacts in the ignored `data/contacts.json`, with an explicit opt-in for each feature. Example structure:

```json
{
  "Sam": {
    "phone": "+14155550123",
    "whatsapp_opt_in": true,
    "call_opt_in": true
  }
}
```

Run `python main.py --setup-whatsapp` and/or `python main.py --setup-twilio` to enter credentials through hidden prompts. Secrets are stored via Windows Credential Manager, not in this file. Existing installs use legacy `Hercules`-prefixed Credential Manager service names; Mercury keeps those internal names so a rebrand does not orphan credentials. Enable only the integrations you configured (`whatsapp_enabled = true`, `twilio_enabled = true`). Inbound WhatsApp also needs `whatsapp_webhook_enabled = true`, both webhook secrets, and a user-managed HTTPS forwarding endpoint. Provider APIs, rules, account eligibility, message windows/templates, and prices can change. Check the official [Meta WhatsApp Business Platform](https://developers.facebook.com/docs/whatsapp/cloud-api/) and [business messaging policy](https://whatsappbusiness.com/policy/), and [Twilio Voice API](https://www.twilio.com/docs/voice/api/call-resource) and [pricing](https://www.twilio.com/voice/pricing) before enabling these features.

## 7. Accuracy benchmark

`python -m accuracy.run` automatically processes all 50 phrases in `accuracy/commands.txt`. For each phrase it prints a three-second countdown and records an eight-second sample, then moves to the next phrase without waiting for Enter. Expect about nine minutes plus model startup; this is finite, but it can look like an unattended loop. Stop it with **Ctrl+C** in the terminal. It prints aggregate detection, confidence, and exact-match totals only; transcripts and audio are not saved or displayed. The score is strict exact-text matching, not command understanding or a guarantee of real-world accuracy.

One local run reported **2/50** exact matches; that is an example of how weak results can be with a particular model, microphone, room, and speaking style, not a benchmark promise. Try the default Windows microphone, speak one phrase naturally, and compare with faster-whisper. Thresholds need empirical tuning. Do not publish your measured score as a general accuracy claim.

## 8. Privacy and local data

- Microphone audio is buffered in memory for segmentation and recognition. Mercury does not write audio recordings to disk.
- Recognized words are kept in memory while the request is routed; Mercury does not print, log, or save the transcript as a transcript. If the local LLM is enabled, the utterance and selected local-file excerpts may be sent to the localhost Ollama process for that response.
- If you enable Google, Meta, or Twilio, the related query/message/call data is transmitted to that provider when you use its features. Read the provider privacy terms.
- Tasks, reminder text, and scheduled-call details are stored in an unencrypted local SQLite database under `data/`. Contact names/numbers/consent flags are in `data/contacts.json`. The confirmation log records tool names and approval outcomes, not speech or tool arguments. These runtime files are Git-ignored but are not encrypted or securely erased.
- OAuth/API secrets are stored using Windows Credential Manager. Security then depends on the Windows account and machine; no secret storage system is perfect.
- Workspace search reads files under the configured path. Treat any files it finds as content provided to the local model; do not include sensitive directories in that workspace.

Before sharing logs, screenshots, database files, settings, or a copy of the repository, check them for private information. Never paste secrets into GitHub issues or chat.

## 9. Safety model

Tools declare their parameters and risk level. Destructive or external actions that are marked `confirm` require a Tkinter approval window; Cancel is the default and errors/timeouts fail closed. This is a guardrail, not a guarantee against every mistaken or malicious request. Read the target, recipient, content, and possible price shown in each prompt before approving. Do not approve an action you did not request.

Folder creation is constrained to the workspace. Deleting an item moves it to the Windows Recycle Bin and is restricted to the workspace. Install commands are restricted to exact allowlisted `winget` package IDs. Websites are opened in a browser but not automated. The LLM cannot run arbitrary shell commands, but local models can still misunderstand a request or produce an inaccurate answer.

## 10. Troubleshooting

**No speech is recognized:** Confirm Windows microphone privacy allows desktop apps; run `--list-devices`, choose a valid `microphone_device`, and use `--doctor`. Try a quiet room and speak after the ready message. Recognition is English-oriented and can perform poorly with noise, distance, accent, or short phrases. Use text mode to separate routing from recognition.

**Replies print but are not audible:** Run `python main.py --test-speech`. Check the Windows output device and volume, and whether a SAPI voice is installed. This test isolates speech output; it does not test recognition.

**The app says the model or Python package is missing:** Run `python --version` and install dependencies using the `.venv` interpreter. Ensure the Vosk archive was extracted to the exact documented path. Faster-whisper needs its model download on first use.

**A confirmation window does not appear:** Run voice mode from an interactive desktop session. If the confirmation service cannot display the window, the action should be refused. Do not close the app while expecting an action to complete.

**Ollama is unavailable:** Start Ollama locally, download the configured model, check its exact tag in `local_ai_model`, and run `--doctor`. The app intentionally refuses a non-local AI endpoint.

**An account feature fails:** Check that its `*_enabled` setting is true, the provider setup is complete, required permissions/scopes are granted, the contact is allowlisted and opted in, and the provider currently supports the selected API/version and account. Error responses avoid displaying credentials. No live account tests are included.

## 11. Limitations and non-goals

- This is an experimental Windows-only Python prototype. No installer, GUI dashboard, background Windows service, mobile app, or auto-start is included.
- Always-listening mode has no wake word; it keeps the microphone stream open until Esc/exit. There is no guarantee of recognition quality. Language support is English-focused.
- The command parser supports specific patterns. Open-ended questions need Ollama; unsupported requests should be refused or reported as unknown. Mercury is not “able to do anything.”
- The app does not automate websites or interact with arbitrary screen contents. Opening ChatGPT or Sheets opens a URL only.
- There is no OCR for image-only PDFs, no encrypted local database, no multi-user authorization, and no native Windows toast notification.
- External calls, WhatsApp delivery, and Google API access depend on provider policies, account permissions, regional availability, network availability, and possible charges.
- No real hardware, external accounts, live phone calls, WhatsApp messages, or install/delete operations were used in automated tests. You must validate your own setup safely.

## Third-party software and models

Mercury depends on separately licensed Python packages declared in `requirements.txt`, including Vosk, faster-whisper (optional at runtime), NumPy, sounddevice, pynput, pyttsx3, Send2Trash, Google API client libraries, keyring, and pypdf. Their licenses and terms remain separate from Mercury's MIT license. Downloaded speech and language models also have their own licenses and terms. Review the relevant project and provider terms before distribution or commercial use. The small Vosk model license is documented in the [official model listing](https://alphacephei.com/vosk/models); Ollama model details are listed in the [official model library](https://ollama.com/library/llama3.2).
