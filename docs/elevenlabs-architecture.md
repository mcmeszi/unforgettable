# ElevenLabs Voice Architecture

Unforgettable keeps the original product rule: voice services only run after an explicit user action. Silence is still treated as thinking, not as a prompt for the system to speak.

## Integration Shape

The project has two ElevenLabs integration layers:

1. **App runtime layer**: PHP endpoints call ElevenLabs REST APIs from the backend. API keys never go to the browser.
2. **Agent/MCP layer**: local AI clients can run the official `elevenlabs-mcp` server for development, automation, and richer agent workflows.
3. **Conversational agent layer**: ElevenLabs server tools can call the app through one authenticated gateway endpoint.

This split keeps the shared-hosting app deployable while still aligning the architecture with the ElevenLabs MCP tool model.

## App Runtime Mapping

| Unforgettable need | Backend endpoint | ElevenLabs capability |
| --- | --- | --- |
| Audio transcript after recording | `/api/transcribe.php` | Speech to Text / Scribe |
| Read back output | `/api/elevenlabs-tts.php` | Text to Speech |
| Voice selection | `/api/elevenlabs-voices.php` | Voice listing/search |
| Subscription/API health | `/api/elevenlabs-status.php` | User subscription |
| Protected playback | `/api/audio-file.php` | Authenticated local audio stream |
| Agent tool gateway | `/api/elevenlabs-agent-tool.php` | Conversational AI server tool endpoint |
| Post-call webhook | `/api/elevenlabs-webhook.php` | Conversational AI post-call webhook |

Raw uploaded recording files are stored only under `data/tmp` during STT and deleted immediately after processing. Generated TTS files are stored under `data/audio` and streamed through an authenticated endpoint.

## MCP Server Setup

The official MCP server is `elevenlabs/elevenlabs-mcp`:

```text
https://github.com/elevenlabs/elevenlabs-mcp
```

The reference repository currently exposes these MCP tools:

```text
text_to_speech, speech_to_text, text_to_sound_effects, search_voices,
list_models, get_voice, voice_clone, isolate_audio, check_subscription,
create_agent, add_knowledge_base_to_agent, list_agents, get_agent,
get_conversation, list_conversations, speech_to_speech, text_to_voice,
create_voice_from_preview, make_outbound_call, search_voice_library,
list_phone_numbers, play_audio, compose_music, create_composition_plan
```

It can be configured in MCP clients with:

```json
{
  "mcpServers": {
    "ElevenLabs": {
      "command": "uvx",
      "args": ["elevenlabs-mcp"],
      "env": {
        "ELEVENLABS_API_KEY": "YOUR_KEY",
        "ELEVENLABS_MCP_OUTPUT_MODE": "files"
      }
    }
  }
}
```

On Windows, if `uvx` is not found by the MCP client, use the absolute `uvx` path in `command`.

This repository also includes an app-local example:

```text
config/elevenlabs-mcp-config.example.json
```

The project also includes a local setup runner:

```bash
php scripts/setup-elevenlabs-agent.php
```

It creates or reuses the `Unforgettable Archivista` Conversational AI agent and
stores the `agent_id` in local app settings. If `public_base_url` is not set, it
creates the agent personality but leaves HTTP server tools disabled, because
ElevenLabs cannot call a `localhost` app.

For local desktop work, prefer:

- `ELEVENLABS_MCP_OUTPUT_MODE=files`
- `ELEVENLABS_MCP_BASE_PATH=<project>/data/audio`

For cloud/client environments without direct filesystem access, use
`resources` or `both` output mode.

## MCP vs App Runtime

| Need | Best layer |
| --- | --- |
| Shared-hosting production STT/TTS | PHP REST endpoints |
| Local creative/audio production | ElevenLabs MCP |
| Create/update ElevenLabs Conversational AI agents | ElevenLabs MCP |
| Agent runtime calling Unforgettable archive/actions | `/api/elevenlabs-agent-tool.php` |
| Post-call capture from ElevenLabs conversations | `/api/elevenlabs-webhook.php` |
| Voice library exploration/design | ElevenLabs MCP |
| In-app readback button | PHP REST endpoint |

## App Configuration

Set the API key in either:

- `config/secrets.php`
- the Settings page inside the app
- the environment variable `ELEVENLABS_API_KEY`

Set the live app URL for server tools in either:

- `config/local.secrets.php` as `public_base_url`
- the Settings page
- `UNFORGETTABLE_PUBLIC_BASE_URL`

Recommended defaults:

- audio provider: `browser` until the key is verified
- STT model: `scribe_v2`
- TTS model: `eleven_multilingual_v2`
- language code: `hu`
- default voice ID: `pNInz6obpgDQGcFmaJgB` (`Adam`)

## Permission Boundary

An all-scope ElevenLabs key only authorizes ElevenLabs operations: voice listing,
speech-to-text, text-to-speech, voice/agent workflows, and future ElevenLabs MCP
tools. It does not authorize Gmail, Google Docs, Google Drive, or OpenAI calls.

Unforgettable therefore uses a separate action layer:

| Action | Required credential/config | Current app behavior |
| --- | --- | --- |
| ElevenLabs STT/TTS | `ELEVENLABS_API_KEY` or Settings key | Direct backend REST call |
| OpenAI summary | `OPENAI_API_KEY`, optional `OPENAI_MODEL` | Direct `/v1/responses` call |
| Email export | `UNFORGETTABLE_EMAIL_TO`, `UNFORGETTABLE_EMAIL_FROM`, `email_enabled` | PHP `mail()` when enabled, otherwise prepared file |
| Google Docs | `GOOGLE_DOCS_FOLDER_ID`, future OAuth/service account adapter | Prepared Markdown payload |
| Drive export | `drive_enabled` | Queued/stub metadata until a Drive adapter is wired |

All outbound actions are explicit button clicks and are logged under
`data/actions`. Keys are never returned to the browser by settings APIs.

Agent-triggered actions use a separate machine secret:

- `ELEVENLABS_AGENT_TOOL_SECRET` for server tool calls
- `ELEVENLABS_WEBHOOK_SECRET` for post-call webhooks

The current gateway supports `search_archive`, `get_session`, `save_memory`,
`append_memory`, `prepare_email`, `prepare_google_doc`, and
`send_openai_summary`. The agent blueprint lives in
`config/elevenlabs-agent-blueprint.json`.

## Cost Discipline

ElevenLabs calls may consume credits. The app therefore avoids automatic/proactive calls:

- recording uses ElevenLabs STT only when the audio provider is set to `elevenlabs`
- readback uses ElevenLabs TTS only when the user clicks the readback button
- status and voice search run only from explicit settings buttons

## Future MCP-First Expansion

V2 can add an MCP bridge process for local desktop deployments:

- call MCP `speech_to_text` instead of direct REST when a local MCP runtime is available
- use MCP `text_to_speech` for generated outputs and richer voice controls
- expose MCP tools for `isolate_audio`, `speech_to_speech`, and voice library workflows
- keep PHP REST as the shared-hosting fallback
