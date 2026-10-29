# Mercury Architecture

## Runtime path

```text
Microphone stream or terminal input
          |
          v
Speech segmentation -> speech recognizer -> confidence / command matching
          |                                      |
          +--------------------------------------v
                                      CommandRouter.handle(text)
                                                 |
                                 registered ToolRegistry actions
                                      |                   |
                               local data/actions     confirmation gate
                                      |
                         printed reply + Windows speech output
```

Voice and text modes share `CommandRouter.handle()`. The microphone module opens a 16 kHz mono signed-16-bit stream, buffers frames in memory, detects speech using a simple RMS threshold, and emits a phrase after roughly 0.75 seconds of silence (or a maximum utterance length). It resets/drops captured input while a reply is being processed to avoid immediately hearing its own TTS. The listener exits on Esc.

The speech-recognition interface is defined in `audio/recognition.py`. Vosk and faster-whisper adapters return text and a confidence estimate. The selected adapter is configured in `settings.toml`. `core/command_match.py` performs conservative matching of known command phrases. The router handles implemented phrases and then, if enabled, calls the local Ollama assistant.

## Tools and approvals

`core/tools.py` defines the registry. Each registered tool declares its name, parameter schema, risk level, function, optional preflight, and confirmation details. The registry validates parameters and refuses unregistered tool names. A `confirm` tool checks preflight conditions, shows an explicit Tkinter approval dialog, writes only tool name and approval result to the confirmation logger, and calls the function only after approval. Cancellation, timeout, an unavailable handler, or dialog failure refuses the operation.

The router still recognizes known phrases before consulting the LLM. When the model is used, it receives only registered tool schemas. The app validates one tool request, executes at most one, then asks the model to phrase the result. The local model endpoint is restricted to HTTP on localhost. The Ollama assistant holds up to six previous assistant replies in memory; recognized user text is not placed into this history or saved by Mercury.

## Main modules

| Path | Responsibility |
| --- | --- |
| `main.py` | Parse command-line modes; wire settings, storage, adapters, tools, integrations, schedulers, and modes. |
| `audio/microphone.py` | Continuous microphone stream, in-memory silence segmentation, device listing, Esc handling. |
| `audio/speech_to_text.py` | Vosk adapter and recognizer factory. |
| `audio/faster_whisper.py` | Optional English `small.en` CPU/int8 adapter. |
| `audio/speech_output.py` | Print public replies and send them through Windows SAPI; private confidence questions are spoken without printing their transcript. |
| `core/router.py` | Parse supported natural-language command patterns and call registered tools. |
| `core/tools.py` | Tool schemas, registration, parameter validation, risk checks, optional-feature registration. |
| `core/confirm.py` | Main-thread Tkinter confirmation dialog with cancel-default timeout and worker queue. |
| `core/settings.py` | TOML parsing, validation, and path resolution. |
| `core/local_ai.py` | Local Ollama chat and registry-constrained tool selection. |
| `core/google_workspace.py` | Official Gmail/Calendar OAuth and API wrapper. |
| `core/communications.py` | Official WhatsApp Business and Twilio HTTP clients. |
| `core/whatsapp_inbox.py` | Local webhook listener, HMAC verification, and bounded in-memory message inbox. |
| `core/contacts.py` | Local contact allowlist and per-feature opt-in checks. |
| `tools/tasks.py` | SQLite task storage and command helpers. |
| `tools/reminders.py` | SQLite reminder/timer storage and in-process scheduler. |
| `tools/scheduled_calls.py` | SQLite call scheduling and dispatch queue. |
| `tools/desktop.py` | Allowlisted app/site opening, workspace folder creation, browser search opening. |
| `tools/system_actions.py` | Confirmed allowlisted winget installs and workspace-only Recycle Bin deletion. |
| `tools/workspace.py` and `tools/document_extract.py` | Bounded read-only local workspace search and supported document text extraction. |
| `tools/project_builder.py` | Questionnaire, approval, spec creation, local Codex CLI invocation, reviewed checkpoint. |
| `core/doctor.py` | Read-only local dependency/configuration status report. |

## State and privacy

Runtime SQLite data and contact files live under ignored `data/`. They are local plaintext, not encrypted. Models live under ignored `model/` or the package's external model cache. Provider secrets are stored in Windows Credential Manager. Recognition audio and transcript are handled in memory; audio is not written to disk, and the confirmation log contains no speech or tool arguments. Enabling integrations intentionally sends feature-specific data to their providers.

## Test strategy

The test suite injects fake microphones, recognizers, speech engines, API clients, clocks, confirmation presenters, and subprocess runners. Storage tests use temporary directories. Automated tests should never access a real microphone, personal database, provider account, installer, or destructive file operation. These tests validate code paths and safety checks; they are not end-to-end hardware/provider certification.
