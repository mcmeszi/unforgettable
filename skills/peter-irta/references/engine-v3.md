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

A jelenlegi aggregált `benchmark-results.json` a 30 briefet `briefs` alatt
tartalmazza, míg a vakteszt-preparáló `generation_jobs` nevű kompatibilitási
nézetet vár. Az alábbi PowerShell-blokk ezt a minimális, gitignore-olt nézetet
reprodukálhatóan állítja elő: az ID-t és a műfajt az aggregált eredményből, a
brief szövegét a publikus generálási jobokból veszi. A blokk ellenőrzi a 30
egyedi ID-t, a műfajonkénti három briefet, a 60 jobot, az A/B párt és a két
forrás azonos ID-/műfajkészletét. Candidate mappinget, source ID-t és
provenance-adatot nem másol a kompatibilitási fájlba.

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
$compatInput = Join-Path $skillRoot "state\human-blind-test-30-input.json"

$benchmark = Get-Content -Raw -LiteralPath `
  (Join-Path $benchmarkRoot "evaluation\benchmark-results.json") | ConvertFrom-Json
$resultRows = @($benchmark.briefs)
$jobs = @(Get-Content -LiteralPath (Join-Path $benchmarkRoot "generation-jobs.jsonl") |
  Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })

if ($resultRows.Count -ne 30 -or
    @($resultRows.brief_id | Sort-Object -Unique).Count -ne 30) {
  throw "A benchmarkeredményben nem 30 egyedi brief van."
}
$genreCounts = @($resultRows | Group-Object genre)
if ($genreCounts.Count -ne 10 -or
    @($genreCounts | Where-Object Count -ne 3).Count -ne 0) {
  throw "A benchmarkeredmény nem 10 műfaj × 3 brief."
}
$jobGroups = @($jobs | Group-Object brief_id)
if ($jobs.Count -ne 60 -or $jobGroups.Count -ne 30 -or
    @($jobGroups | Where-Object Count -ne 2).Count -ne 0) {
  throw "A generálási jobok nem 30 darab kétjelöltes párt alkotnak."
}
if (Compare-Object @($resultRows.brief_id | Sort-Object) @($jobGroups.Name | Sort-Object)) {
  throw "A benchmarkeredmény és a generálási jobok brief-ID készlete eltér."
}

$compatRows = foreach ($row in $resultRows) {
  $matching = @($jobs | Where-Object brief_id -eq $row.brief_id)
  $candidates = @($matching.candidate | Sort-Object -Unique)
  $genres = @($matching.genre | Sort-Object -Unique)
  $briefs = @($matching.brief | Sort-Object -Unique)
  if (($candidates -join ",") -ne "A,B" -or
      $genres.Count -ne 1 -or $genres[0] -ne $row.genre -or
      $briefs.Count -ne 1 -or [string]::IsNullOrWhiteSpace($briefs[0])) {
    throw "Eltérő A/B jobadat: $($row.brief_id)"
  }
  [ordered]@{
    brief_id = [string]$row.brief_id
    genre = [string]$row.genre
    brief = [string]$briefs[0]
  }
}
[ordered]@{ generation_jobs = @($compatRows) } |
  ConvertTo-Json -Depth 4 |
  Set-Content -LiteralPath $compatInput -Encoding utf8

python "$skillRoot\scripts\prepare_human_blind_test.py" `
  --results "$compatInput" `
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
  --progress "$humanTestRoot\progress.json" `
  --result "$humanTestRoot\human-result.json" `
  --host 127.0.0.1 `
  --port 0
```

A 30 döntés véglegesítése emberi evidenciát hoz létre. Nem ír automatikusan
retrieval-utility bejegyzést, nem állít elő voice-feedback ledgerbejegyzést, és
nem hoz létre tanult preference-et; az eredményben ezért
`utility_written=false`, `learned_preference_claimed=false` és
`feedback_review_required=true` szerepel.
