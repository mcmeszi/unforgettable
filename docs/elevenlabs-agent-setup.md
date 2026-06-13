# ElevenLabs Agent Setup

Ez a réteg az Unforgettable appot ElevenLabs Conversational AI agentként is
használhatóvá teszi.

## Official MCP role

Az ElevenLabs hivatalos MCP szervere:

```text
https://github.com/elevenlabs/elevenlabs-mcp
```

Ebben a projektben két külön szerepe van:

1. **Builder role**: MCP-vel lehet ElevenLabs oldalon agentet, voice-t,
   knowledge base kapcsolatot, conversation lekérést és audio asseteket
   létrehozni.
2. **Runtime app role**: az elkészült ElevenLabs agent az Unforgettable appot
   HTTP server toolokon és post-call webhookokon keresztül hívja.

Konfig példa:

```text
config/elevenlabs-mcp-config.example.json
```

Az app-local setup script ugyanazt a hivatalos MCP/SDK konfigurációs alakot
követi, de `uvx` nélkül is futtatható:

```bash
php scripts/setup-elevenlabs-agent.php
```

Viselkedés:

- ha nincs `Unforgettable Archivista` nevű agent, létrehozza
- ha már van ilyen nevű agent, újrahasznosítja
- ha `public_base_url` is be van állítva, újrafuttatáskor frissíteni tudja a
  HTTP tool konfigurációt
- az `agent_id` a `data/settings/app.json` fájlba kerül, API kulcsok nélkül

Az ElevenLabs subscription endpoint `user_read` jogosultságot kérhet. Az app
státuszellenőrzése ezért külön kezeli a tényleges képességeket:
`models`, `voices`, `agents`.

## Miért elég egy endpoint?

Az ElevenLabs server toolok HTTP endpointot hívnak. Az appban ezért egyetlen
gateway endpoint van:

```text
POST /api/elevenlabs-agent-tool.php
```

A tool a JSON `action` mező alapján route-ol:

| Action | Mire való |
| --- | --- |
| `search_archive` | Keresés az Unforgettable session archívumban |
| `get_session` | Konkrét session tartalmának lekérése |
| `save_memory` | Új session mentése agentből |
| `append_memory` | Meglévő session folytatása |
| `prepare_email` | Email export előkészítése/küldése |
| `prepare_google_doc` | Google Docs payload előkészítése |
| `send_openai_summary` | Session összefoglaló küldése OpenAI-ba |

Auth:

```http
Authorization: Bearer {{ELEVENLABS_AGENT_TOOL_SECRET}}
Content-Type: application/json
```

Alternatíva shared hosting teszthez:

```http
X-Unforgettable-Tool-Secret: {{ELEVENLABS_AGENT_TOOL_SECRET}}
```

Az ElevenLabs webhook tool hívások az adatokat `parameters` objektumba is
csomagolhatják. A gateway mindkét alakot elfogadja:

```json
{
  "tool_name": "search_archive",
  "parameters": {
    "action": "search_archive",
    "query": "buszmegállós vers",
    "limit": 5
  }
}
```

## Agent személyiség

A konfigurációs blueprint:

```text
config/elevenlabs-agent-blueprint.json
```

Alapelvek:

- magyarul beszél
- nem szakítja meg a gondolkodást
- a csendet gondolkodásnak tekinti
- nem értékeli automatikusan a kreatív anyagot
- keresést, mentést, emailt, Google Docsot és OpenAI továbbítást csak explicit kérésre indít
- az eredeti anyagot és saját javaslatot mindig elválasztja

## Post-call webhook

Webhook endpoint:

```text
POST /api/elevenlabs-webhook.php
```

Auth:

- elsődleges: ElevenLabs aláírás `ElevenLabs-Signature` headerrel
- fallback/shared hosting teszt: `X-Unforgettable-Webhook-Secret`

Secret:

```text
ELEVENLABS_WEBHOOK_SECRET
```

Lokális/shared-hosting smoke teszthez használható a custom header:

```http
X-Unforgettable-Webhook-Secret: {{ELEVENLABS_WEBHOOK_SECRET}}
```

Éles ElevenLabs workspace webhooknál a publikus URL kötelező. A helyi
`127.0.0.1` vagy `localhost` címet az ElevenLabs szerverei nem tudják elérni.

Viselkedés:

- nyers webhook payload mentése `data/actions` alá
- transcript/summary kinyerése ismert mezőkből
- ha van szöveg, automatikus Unforgettable session létrehozása

## ElevenLabs keresés kontra saját keresés

Az ElevenLabs knowledge base search akkor lehet jó fő kereső, ha az
Unforgettable archívumot rendszeresen szinkronizáljuk ElevenLabs Knowledge
Base-be. Ez később MCP-vel vagy cron jobbal megoldható.

A jelenlegi appban az elsődleges kereső a `search_archive` tool, mert az mindig
a helyi JSON session fájlok aktuális állapotát látja, és nincs külön indexelési
késleltetés.

Ajánlott stratégia:

1. Agent runtime: `search_archive` tool.
2. Nagy tudásanyag: ElevenLabs Knowledge Base.
3. Hibrid mód: agent először saját archívumban keres, majd ha nincs találat,
   ElevenLabs KB search vagy külső kutatás következhet.

## MCP tool mapping

| Unforgettable cél | ElevenLabs MCP tool |
| --- | --- |
| Felolvasás, hangminták | `text_to_speech` |
| Beszéd leiratozása | `speech_to_text` |
| Hangok keresése saját libraryben | `search_voices` |
| Publikus voice library keresés | `search_voice_library` |
| Voice design preview | `text_to_voice` |
| Preview mentése voice-ként | `create_voice_from_preview` |
| Conversational agent létrehozása | `create_agent` |
| Agent ellenőrzése | `get_agent`, `list_agents` |
| Knowledge Base hozzáadása agenthez | `add_knowledge_base_to_agent` |
| Conversation transcript lekérése | `get_conversation`, `list_conversations` |
| Post-call sync az appba | `POST /api/elevenlabs-webhook.php` |
| App archívumkeresés agentből | `POST /api/elevenlabs-agent-tool.php` |
| Outbound telefonhívás agenttel | `make_outbound_call` |

## Környezeti változók

```text
ELEVENLABS_API_KEY=...
ELEVENLABS_AGENT_TOOL_SECRET=...
ELEVENLABS_WEBHOOK_SECRET=...
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1
OPENAI_SUMMARY_MODEL=gpt-4.1
UNFORGETTABLE_PUBLIC_BASE_URL=https://your-live-domain.example
UNFORGETTABLE_EMAIL_TO=...
UNFORGETTABLE_EMAIL_FROM=...
GOOGLE_DOCS_FOLDER_ID=...
GOOGLE_DOCS_REFRESH_TOKEN=...
GOOGLE_DOCS_CLIENT_ID=...
GOOGLE_DOCS_CLIENT_SECRET=...
GOOGLE_DOCS_SERVICE_ACCOUNT_JSON_PATH=...
```

## Példa server tool body

```json
{
  "action": "search_archive",
  "query": "{{user_query}}",
  "limit": 5
}
```

```json
{
  "action": "save_memory",
  "title": "{{short_title}}",
  "text": "{{conversation_summary_or_user_text}}",
  "important": false
}
```
