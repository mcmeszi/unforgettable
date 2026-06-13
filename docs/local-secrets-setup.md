# Local Secrets Setup

Do not paste API keys into chat or commit them to Git.

Use this local, ignored file:

```text
config/local.secrets.php
```

Set:

```php
'elevenlabs_api_key' => 'YOUR_ELEVENLABS_API_KEY',
```

The app also reads these environment variables if the local file does not
override them:

```text
ELEVENLABS_API_KEY
ELEVENLABS_AGENT_TOOL_SECRET
ELEVENLABS_WEBHOOK_SECRET
OPENAI_API_KEY
OPENAI_MODEL
OPENAI_SUMMARY_MODEL
UNFORGETTABLE_PUBLIC_BASE_URL
GOOGLE_DOCS_FOLDER_ID
GOOGLE_DOCS_ACCESS_TOKEN
GOOGLE_DOCS_REFRESH_TOKEN
GOOGLE_DOCS_CLIENT_ID
GOOGLE_DOCS_CLIENT_SECRET
GOOGLE_DOCS_SERVICE_ACCOUNT_JSON
GOOGLE_DOCS_SERVICE_ACCOUNT_JSON_PATH
```

`ELEVENLABS_AGENT_TOOL_SECRET` and `ELEVENLABS_WEBHOOK_SECRET` protect the
Unforgettable HTTP endpoints that ElevenLabs agents call. They are not
ElevenLabs account keys.

After the ElevenLabs API key is present, the next steps are:

1. Verify ElevenLabs capability status.
2. Run:
   ```bash
   php scripts/setup-elevenlabs-agent.php
   ```
3. The script creates or reuses the ElevenLabs agent and stores the resulting
   agent ID in `data/settings/app.json` without copying API keys there.
4. For live ElevenLabs server tools, set:
   ```php
   'public_base_url' => 'https://your-live-domain.example',
   ```
   then rerun the setup script. Localhost cannot be called by ElevenLabs.
5. Configure post-call webhook to:
   ```text
   https://your-live-domain.example/api/elevenlabs-webhook.php
   ```

`GOOGLE_DOCS_FOLDER_ID` only names the target folder. Native Google Docs/Drive
creation also needs OAuth (`google_docs_refresh_token` + client credentials) or
a service account JSON credential. If using a service account, share the target
Drive folder with that service account email.
