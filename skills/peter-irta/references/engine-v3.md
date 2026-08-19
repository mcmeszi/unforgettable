# Mind Vault Engine v3

Az Engine a vékony `peter-irta` skill és a meglévő RAG közötti helyi orchestration-réteg. Nem MCP-szerver: a skill ugyanabban a folyamatban futtatja, és egy brief-specifikus evidence packetet kap vissza.

## Alapfuttatás

```powershell
python scripts/mind_vault_engine.py `
  --brief "Írj rövid válasz emailt: előbb válaszolj, majd adj következő lépést." `
  --genre email `
  --audience "kolléga" `
  --output state/engine-packet.json
```

A `--genre` elhagyható, ha a briefből egyértelműen felismerhető. Bizonytalan műfajnál add meg explicit. A `--dialogue required` kényszeríti, a `--dialogue off` letiltja a dialóguskalibrációt. A hangtengelyek ismételhető `--target-axis axis=0..1` argumentummal adhatók át.

## Packet-szerződés

- `brief_plan`: explicit, kikövetkeztetett és hiányzó briefmezők, plusz negatív preferenciák;
- `channels.content`: briefhez releváns saját források;
- `channels.style_mechanics`: ritmus- és mechanikaankorok;
- `channels.dialogue`: kizárólag aggregált Slack-kalibráció, nyers üzenet nélkül;
- `channels.negative_examples`: műfaji guardok, briefbeli tiltások és valid, de céltól távoli Péter-tartományok;
- `preference_reranker`: brief-fit + visszamért generation utility, zsugorított és korlátozott súllyal;
- `evidence_compiler`: a generálásnak átadható 3–5 mechanika, evidence és kötelező korlát.

## Döntési szabályok

1. Friss műfaji feedback erősebb a közvetlen műfaji korpusznál; az erősebb a Slack-profilnál; az erősebb a globális heurisztikánál.
2. `strong` dialógusátadás műfaji kalibrációként automatikusan használható. `conditional` csak dialógus- vagy válaszhelyzetnél aktív. `dialogue-only` kizárólag explicit dialógusrészletnél aktív.
3. A Slack nem tény-, idézet-, képi, rímbeli vagy zenei forrás.
4. A preference-reranker `cold-start`, amíg nincs elegendő visszamért forrásszintű utility. Ilyenkor nem változtatja meg tanult preferenciaként a retrievalt.
5. A negatív csatorna határjelző. A `contrast_set` nem rossz szöveg, hanem Péter egy másik, ehhez a briefhez nem célzott tartománya.

## Visszacsatolás

Elfogadás vagy elutasítás után a már meglévő `retrieval_feedback.py` rögzíti az execution source ID-k utilityját. Egy forrás csak legalább három műfajazonos megfigyelés után kap zsugorított súlyt; a nyers brief és a draft nem kerül a ledgerbe.

## Reprodukálható generálás és műfaji kritika

Az Engine packetből futtatófüggetlen generálási és kritikai job készíthető:

```powershell
python scripts/generation_critique_workflow.py `
  --engine-packet state/engine-packet.json `
  --variation-seed slam-01 `
  --output-dir state/workflows/slam-01
```

A publikus `generation-critique-job.json` csak vak `S1`–`S4` evidence-címkéket
tartalmaz. A valódi source ID-k a külön `private-generation-manifest.json`
fájlban maradnak. A generált draft ugyanahhoz a kritikajobhoz köthető a `--draft`
kapcsolóval; ekkor a workflow a szöveg SHA-256 hashét is rögzíti. A kritika a négy
független eredménytengelyt és a műfaji hard guardokat kapja meg. Utility csak
emberi elfogadás vagy elutasítás után rögzíthető.

## V1 vs Engine v3 vak benchmark

Az azonos RAG-snapshoton futó, briefenként fix seedű retrieval-párok:

```powershell
python scripts/run_engine_v3_benchmark.py --output state/engine-v3-benchmark-latest.json
python scripts/prepare_generation_benchmark.py `
  --retrieval state/engine-v3-benchmark-latest.json `
  --output-dir state/engine-v3-generation-benchmark
```

Az összes sorrendcserés ítélet elkészülte után a validálás, hash-fagyasztás,
feloldás és aggregálás egy menetben futtatható:

```powershell
$root = "state/engine-v3-generation-benchmark"
python scripts/aggregate_engine_v3_benchmark.py `
  --jobs "$root/evaluation/evaluation-jobs.jsonl" `
  --judgments-dir "$root/evaluation/judgments" `
  --order-key "$root/evaluation/private-order-key.json" `
  --blind-key "$root/blind-key.json" `
  --manifest "$root/evaluation/judgment-manifest.json" `
  --output "$root/evaluation/benchmark-results.json" `
  --report "$root/evaluation/benchmark-report.md"
```

A publikus `generation-jobs.jsonl` nem tartalmazza a `legacy`/`engine_v3`
mappinget vagy valódi source ID-t. Ezek a `blind-key.json` és a
`private-generation-manifest.json` fájlban maradnak. A blind key csak az összes
draft és sorrendcserés kritika lezárása után oldható fel. A benchmark önmagában
nem ír utility ledgert és nem bizonyít tanult preference-hatást.

## Helyi, 30 páros emberi vakteszt

A vakteszt a már lezárt generálási benchmarkból készül; nem futtat retrievalt
vagy modellhívást. Emiatt ehhez a lépéshez a `MIND_VAULT_RAG_ROOT` nem kell.
Csak akkor állítsd be, ha az előző fejezet retrieval-benchmarkját is újragenerálod:

```powershell
$repoRootText = git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoRootText)) {
  throw "A parancsot a kisagy Git-repón belül futtasd."
}
$repoRoot = [IO.Path]::GetFullPath($repoRootText.Trim())
$ragRoot = Join-Path $repoRoot "data\mind-vault\rag"
if (-not (Test-Path -LiteralPath $ragRoot -PathType Container)) {
  throw "Nem található RAG-gyökér: $ragRoot"
}
$env:MIND_VAULT_RAG_ROOT = $ragRoot
```

A vakteszt-preparáló közvetlenül fogadja az aggregált
`evaluation\benchmark-results.json` hivatalos, `briefs` alatti alakját. Az ID-t
és a műfajt ebből ellenőrzi, a publikus brief szövegét pedig a meglévő
`generation-jobs.jsonl` azonos A/B párjából kapcsolja hozzá. Külön
kompatibilitási JSON nem kell. A preparáló ellenőrzi a 30 egyedi ID-t, a
műfajonkénti három briefet, a 60 jobot, az A/B párokat, az azonos briefszöveget,
valamint a result/job ID- és műfajegyezést.

```powershell
$repoRootText = git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoRootText)) {
  throw "A parancsot a kisagy Git-repón belül futtasd."
}
$repoRoot = [IO.Path]::GetFullPath($repoRootText.Trim())
$skillRoot = Join-Path $repoRoot "skills\peter-irta"
$runtimeSkillRoot = Join-Path $env:USERPROFILE ".codex\skills\peter-irta"
$benchmarkRoot = Join-Path $runtimeSkillRoot "state\engine-v3-generation-benchmark"
$humanTestRoot = Join-Path $skillRoot "state\human-blind-test-30"

python "$skillRoot\scripts\prepare_human_blind_test.py" `
  --results "$benchmarkRoot\evaluation\benchmark-results.json" `
  --jobs "$benchmarkRoot\generation-jobs.jsonl" `
  --drafts-dir "$benchmarkRoot\drafts" `
  --blind-key "$benchmarkRoot\blind-key.json" `
  --seed 20260818 `
  --output-dir "$humanTestRoot"
```

A preparáló szándékosan visszautasítja a nem üres output könyvtárat. Új körhöz
adj új outputnevet; meglévő emberi futást ne írj felül.

Az elkészült tesztet kizárólag loopbacken indítsd. A szerver a kiválasztott
szabad portot JSON-ként kiírja; azt nyisd meg `http://127.0.0.1:<port>/` címen.

```powershell
$repoRootText = git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoRootText)) {
  throw "A parancsot a kisagy Git-repón belül futtasd."
}
$repoRoot = [IO.Path]::GetFullPath($repoRootText.Trim())
$skillRoot = Join-Path $repoRoot "skills\peter-irta"
$humanTestRoot = Join-Path $skillRoot "state\human-blind-test-30"

python "$skillRoot\scripts\human_blind_test_server.py" `
  --public "$humanTestRoot\public-test.json" `
  --private "$humanTestRoot\private-human-key.json" `
  --manifest "$humanTestRoot\human-test-manifest.json" `
  --progress "$humanTestRoot\human-test-progress.json" `
  --result "$humanTestRoot\human-test-result.json" `
  --host 127.0.0.1 `
  --port 0
```

A mutációs végpontok csak `application/json` kérést fogadnak, a `Host`
fejlécnek a tényleges `127.0.0.1:<port>` authorityval, a jelen levő `Origin`
fejlécnek pedig ugyanennek a HTTP originjével kell egyeznie. Origin nélküli,
helyi CLI-kérés megengedett, ha a Host pontos. Távoli bind, cross-origin írás
és DNS-rebinding Host tilos.

A 30 döntés véglegesítése emberi evidenciát hoz létre. Nem ír automatikusan
retrieval-utility bejegyzést, nem állít elő voice-feedback ledgerbejegyzést, és
nem hoz létre tanult preference-et; az eredményben ezért
`utility_written=false`, `learned_preference_claimed=false` és
`feedback_review_required=true` szerepel.

## Finalizált emberi evidence importja és kézi kurálása

Az alábbi parancsokat a `kisagy` repository gyökeréből futtasd. A finalizált
eredményt és a hozzá tartozó private keyt immutable inputként kezeld: az import
csak a lokális, gitignore-olt evidence ledgerhez fűz új `pending_review`
megfigyeléseket.

```powershell
python skills/peter-irta/scripts/import_human_blind_feedback.py `
  --result skills/peter-irta/state/human-blind-test-30/human-test-result.json `
  --private-key skills/peter-irta/state/human-blind-test-30/private-human-key.json `
  --ledger skills/peter-irta/state/evidence-vault/evidence.jsonl
```

A `pending_review` megfigyelések kilistázása:

```powershell
python skills/peter-irta/scripts/curate_evidence.py list `
  --evidence-ledger skills/peter-irta/state/evidence-vault/evidence.jsonl `
  --decision-ledger skills/peter-irta/state/evidence-vault/decisions.jsonl
```

Egy guard létrehozása és ugyanabban a tranzakcióban történő aktiválása:

```powershell
python skills/peter-irta/scripts/curate_evidence.py create-derived `
  --evidence-ledger skills/peter-irta/state/evidence-vault/evidence.jsonl `
  --decision-ledger skills/peter-irta/state/evidence-vault/decisions.jsonl `
  --type guard `
  --genre slam `
  --scope spoken_delivery `
  --scope speaker_coherence `
  --directive "A slam egyszeri hallásra követhető, kimondható előadói ívet tartson; a beszélők viszonya és minden megszólalás gazdája legyen világos." `
  --guard-level hard `
  --confidence high `
  --basis "Kurált emberi feedback: slam-03." `
  --parent-run hbt-db17d34b356b8f33f6d3dcf2 `
  --parent-brief slam-03 `
  --activate
```

Mechanizmusnál ugyanaz a folyamat, de `--type mechanism` kell, és nincs
`--guard-level`:

```powershell
python skills/peter-irta/scripts/curate_evidence.py create-derived `
  --evidence-ledger skills/peter-irta/state/evidence-vault/evidence.jsonl `
  --decision-ledger skills/peter-irta/state/evidence-vault/decisions.jsonl `
  --type mechanism `
  --genre reklam `
  --scope first_obvious_ad_concept `
  --scope campaign_coherence `
  --directive "Az első evidens koncepciót vizsgáld felül, majd az insight–koncepció–kibontás–CTA láncot egyetlen stratégiai csavarrá zárd." `
  --confidence high `
  --basis "Kurált emberi feedback: reklam-02, reklam-03." `
  --parent-run hbt-db17d34b356b8f33f6d3dcf2 `
  --parent-brief reklam-02 `
  --parent-run hbt-db17d34b356b8f33f6d3dcf2 `
  --parent-brief reklam-03 `
  --activate
```

Több szülőnél minden briefhez külön, azonos sorrendű `--parent-run` és
`--parent-brief` párt adj. Egy azonos `create-derived --activate` parancs
ismétlése ugyanazt az evidence ID-t adja vissza, és nem ír duplikált rekordot
vagy döntést.

Az Engine alapértelmezésben beolvassa az aktív derived evidence-et:

```powershell
python skills/peter-irta/scripts/mind_vault_engine.py `
  --brief "Írj egyszeri hallásra követhető slamet." `
  --genre slam `
  --evidence-ledger skills/peter-irta/state/evidence-vault/evidence.jsonl `
  --decision-ledger skills/peter-irta/state/evidence-vault/decisions.jsonl `
  --output skills/peter-irta/state/engine-packet.json
```

Összehasonlító kontrollként szándékosan ki lehet kapcsolni a derived
evidence-et. A `--no-derived-evidence` nem fallback hiba esetére, hanem explicit
kontrollfutás:

```powershell
python skills/peter-irta/scripts/mind_vault_engine.py `
  --brief "Írj egyszeri hallásra követhető slamet." `
  --genre slam `
  --evidence-ledger skills/peter-irta/state/evidence-vault/evidence.jsonl `
  --decision-ledger skills/peter-irta/state/evidence-vault/decisions.jsonl `
  --no-derived-evidence `
  --output skills/peter-irta/state/engine-packet-no-derived.json
```

A human-blind import és a `curate_evidence.py` kézi review nem ír automatikusan retrieval-utility
vagy voice-feedback bejegyzést. Utility kizárólag a meglévő, explicit emberi
elfogadási/elutasítási folyamatból származhat; a curated rule aktiválása önmagában
nem tanult preference.
