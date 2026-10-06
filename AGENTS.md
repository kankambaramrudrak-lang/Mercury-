# Hercules project rules

- Never log or display recognized speech. Do not add speech-debug output; keep recognized words in memory only long enough to route the command, and never save microphone audio.
- Every risky or destructive action requires a deliberate button confirmation. If that confirmation flow is not implemented, refuse the action without changing data.
- Use official APIs only. Never automate websites or store passwords.
- Make small, scoped changes. Tests must use fake components and temporary data; never use real installs, destructive deletes, microphones, or personal databases in tests.
- At the end of each phase, explain new files in plain English, list all changed files, report checks, and stop for manual review. Do not commit; the user commits changes.
