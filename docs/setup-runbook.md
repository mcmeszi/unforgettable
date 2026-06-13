# Unforgettable Setup Runbook

## Current Focus

Google Docs/Drive is intentionally paused because the OAuth app is blocked by
Google verification/test-user limits. Keep the credentials local for later, but
do not treat Google export as a live workflow for now.

## Doctor

Run:

```bash
php scripts/setup-doctor.php
```

The doctor prints setup status without exposing API keys or tokens.

Main states:

- `OK`: ready
- `PAUSED`: intentionally not active
- `CHECK`: configured enough to continue, but may need attention
- `BLOCKED`: required runtime/config is missing

## Digest Cron

Manual:

```bash
php scripts/cron-digest.php --date 2026-06-12
```

Shared-hosting cron example:

```bash
php /home/USER/path/to/unforgettable/scripts/cron-digest.php --quiet
```

The script writes Markdown digests under:

```text
data/digests/YYYY-MM-DD.md
```

## Active Integrations

- ElevenLabs STT/TTS backend endpoints
- ElevenLabs Conversational AI agent personality
- ElevenLabs authenticated agent tool gateway, ready for a future public URL
- OpenAI summary export
- Email export/preparation
- iOS Notes Shortcut export payload
- Morning digest generation

## Paused Integrations

- Google Docs native creation
- Google Drive direct upload

The app still prepares local Markdown payloads when needed, but live Google
writes should stay off until OAuth verification/test-user access is solved.

