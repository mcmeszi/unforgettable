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
