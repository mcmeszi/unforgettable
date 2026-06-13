# Google Drive and Docs Setup

Unforgettable can now move beyond prepared Markdown files and create native
Google Docs through the Drive upload API when credentials are available.

## Current Runtime Behavior

The app reads:

```php
'google_docs_folder_id' => '...',
'google_docs_access_token' => '...',
'google_docs_refresh_token' => '...',
'google_docs_client_id' => '...',
'google_docs_client_secret' => '...',
'google_docs_service_account_json' => '...',
'google_docs_service_account_json_path' => '...',
```

The folder ID alone is not an authorization credential. If only the folder ID is
set, the app returns `needs_google_auth` and writes a local Markdown payload
under `data/actions`.

## OAuth Refresh Token Mode

Set all three:

```php
'google_docs_refresh_token' => '...',
'google_docs_client_id' => '...',
'google_docs_client_secret' => '...',
```

The app exchanges the refresh token for an access token and uploads session
content as a native Google Doc to the configured folder.

For personal Gmail/Drive accounts, this is the recommended path. Service
accounts can authenticate, but personal Drive uploads may fail with
`storageQuotaExceeded` because the service account would own the uploaded file
and does not have normal Drive storage.

Helper:

```bash
php scripts/google-oauth-connect.php
```

Before running it, create an OAuth client in Google Cloud:

1. APIs & Services -> Credentials.
2. Create Credentials -> OAuth client ID.
3. Application type: Desktop app.
4. Copy the client ID and client secret into `config/local.secrets.php`:

```php
'google_docs_client_id' => '...',
'google_docs_client_secret' => '...',
```

The helper opens a localhost callback at:

```text
http://127.0.0.1:8765/oauth2callback
```

It stores the returned refresh token in `config/local.secrets.php` without
printing it.

## Service Account Mode

Set one of:

```php
'google_docs_service_account_json' => '{...}',
'google_docs_service_account_json_path' => 'C:/path/to/service-account.json',
```

Then share the target Google Drive folder with the service account email
(`client_email` inside the JSON). Without that share, Google may authenticate
successfully but still reject folder writes.

For Google Workspace Shared Drives, service account mode can work if the
service account has write permission on the Shared Drive or folder. For a
personal Google Drive folder, use OAuth refresh token mode instead.

## App Endpoints

- `/api/action-dispatch.php` with `action=google_doc`: create or prepare one
  Google Doc for a session.
- `/api/drive-upload.php`: upload session output, transcript and JSON data as
  Google Docs-native files when Drive is enabled and credentials exist.
- `/api/elevenlabs-agent-tool.php` with `prepare_google_doc`: lets the
  ElevenLabs agent trigger the same Google Doc flow after explicit user request.
