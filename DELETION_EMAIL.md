# Project deletion archive email

After Admin confirms a complete ZIP download and deletes a project, the app queues that exact ZIP for **ayush@tpplpune.com** and attempts delivery immediately after the deletion transaction commits. The existing dispatch-completion recipient setting is separate.

Configure these private **Vercel Production environment variables**, then redeploy:

- `ARCHIVE_MAIL_ENABLED=true`
- `SMTP_HOST`
- `SMTP_PORT` (587 for STARTTLS or 465 for implicit TLS)
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_FROM`

Never commit credentials. Local preview and browser fixtures force email off.

Admins see **Project deletion emails** below the Projects list. Sent means the SMTP service accepted the email, not that it reached the recipient's inbox. Missing configuration leaves it Queued. Failed or interrupted sends retain the private ZIP and require checking provider delivery before retrying to avoid duplicates. Interrupted Sending records can be retried after five minutes and confirmation that the provider did not accept the email.

The private attachment is removed after successful sending; a minimal delivery receipt remains. Download confirmation, snapshot verification and deletion permissions still apply. Downloading a ZIP or rolling back a deletion never sends an email.

The deletion HTTP request performs the first attempt automatically. Vercel does not run a background worker; Admin can retry pending deliveries from Projects. A separately running server can process queued archives using `python send_dispatch_mail.py --watch`. That worker also processes earlier dispatch-completion messages.

Validation: `python -m unittest test_project_deletion test_projects -v` and `python test_browser.py browser-project-delete.cjs`. Tests use disposable local data and mocked email transport; they do not send real messages.
