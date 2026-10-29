# Mercury contributor instructions

- Never log or display recognized speech. Keep speech transcripts in memory only long enough to route the request, and never save microphone audio.
- Risky, external, or destructive actions require deliberate button approval. Cancel, timeout, or a failed confirmation must refuse the action.
- Use official APIs only. Do not automate websites, store passwords, or let an LLM run arbitrary shell commands.
- Keep changes scoped. Tests must use fake components and temporary data; do not use real installs, destructive deletes, microphones, provider accounts, or personal databases in tests.
- Keep setup and privacy documentation aligned with the implementation. Report test evidence and any untested hardware/provider behavior accurately.
- Do not commit or publish unless the user explicitly requests it.
