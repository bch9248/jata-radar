# Security and private data

Keep `.env` and `.local/` out of Git. Use GitHub Actions Secrets rather than committing credentials. Rotate an exposed API key or SMTP password; deleting a commit is not sufficient. Never put applicant names/contact information into public job records.

The issue template does not run submissions automatically. Only maintainers execute URL imports and manual approvals. Tests run offline; update jobs run only on scheduled/manual default-branch workflows.

If you find a vulnerability, notify the maintainer privately using a channel they publish. Do not post active credentials or sensitive logs in an issue.
