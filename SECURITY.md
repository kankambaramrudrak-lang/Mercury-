# Security notes

Mercury is experimental desktop software that can search local files and, when enabled, communicate with external services. Treat it as an unreviewed personal project and enable only the integrations you understand.

## Protect local data

- Do not commit `.env` files, OAuth client JSON, access tokens, WhatsApp/Twilio credentials, `data/`, databases, contact lists, downloaded models, or personal workspace files.
- The repository ignores common runtime and secret paths, but `.gitignore` is not a secret scanner. Review `git status` and the staged diff before publishing.
- Local SQLite databases and contacts are not encrypted. Protect them with your Windows account/device security.
- Keep the configured workspace narrow and free of secrets. Workspace search skips common secret folders and filenames but cannot reliably detect every sensitive file.
- Review every confirmation prompt, especially recipients, message contents, call destinations, install commands, and deletion paths.

## Reporting a vulnerability

Please do not report exploitable details in a public issue. Use GitHub's private vulnerability reporting for the repository if enabled. If private reporting is unavailable, contact the repository owner through the address listed on their GitHub profile and include a concise reproduction, affected version/commit, impact, and a suggested mitigation. Do not include credentials or private data in the report.

No security response-time or support guarantee is offered for this experimental project.
