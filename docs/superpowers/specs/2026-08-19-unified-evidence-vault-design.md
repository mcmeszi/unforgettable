# Egységes Mind Vault evidence-réteg — design

Dátum: 2026-08-19

## 1. Cél

A `peter-irta` skill egyetlen, provenance-kezelt evidence-felületről kapjon
briefspecifikus saját hangmintát, műfaji mechanikát, negatív guardot és — csak
elegendő adat után — retrieval utilityt. Az egységesítés nem mossa össze az
eredeti Péter-szövegeket a V1 vagy Engine v3 által generált draftokkal.

A 30 briefes emberi vakteszt eredménye kurált feedbackforrásként kerül be. A
teszt nem állít globális győztest: Engine v3 8, V1 12, döntetlen 10, erősen
műfajfüggő eloszlással. Emiatt a rendszer nem tanul automatikus V1/Engine
routingot, és a preference-reranker cold-start állapota változatlan marad.

## 2. Nem cél

- A teljes RAG újraépítése vagy az eredeti korpusz átmásolása.
- Generált V1/Engine v3 draftok saját hangmintává emelése.
- Vaktesztből automatikus utility, preference vagy tréningadat készítése.
- Merev `genre -> V1/Engine` útválasztás.
- Release, deploy vagy MCP-adapter.
- Kurátori felület építése; az első verzió átlátható helyi CLI-t használ.

## 3. Döntés

Egy logikailag egységes, típusos evidence vault készül. A fizikai saját
szövegkorpusz és a derived evidence külön marad, de ugyanazon selector
egységes rekordmodelljén keresztül jelenik meg.

Az eredeti RAG-találatok futás közben `voice_source` rekordokká adaptálódnak;
nem duplikáljuk őket. A derived rekordok append-only JSONL ledgerben, a
kurátori státuszváltások külön append-only decision ledgerben maradnak. Az
aktuális állapotot a rekord és az időrendben rá alkalmazott döntések adják.

## 4. Rekordmodell

Minden evidence-rekord kötelező burka:

```json
{
  "schema": "mind-vault-evidence/v1",
  "evidence_id": "ev-<24 hex>",
  "evidence_type": "evaluation_observation",
  "genre": ["slam"],
  "scope": ["spoken_delivery"],
  "status": "pending_review",
  "authority": "evaluation_only",
  "content": {},
  "provenance": {
    "source_kind": "human_blind_test",
    "source_run_id": "hbt-<24 hex>",
    "source_item_id": "item-01",
    "brief_id": "slam-01",
    "source_sha256": "<64 hex>"
  },
  "confidence": {
    "level": "medium",
    "basis": "single explicit human comparison"
  },
  "created_at": "<ISO-8601 UTC>",
  "supersedes": []
}
```

A `scope` normalizált, policyben engedélyezett fogalmakat tartalmaz. Ez köti
össze az ugyanarra a jelenségre vonatkozó guardokat és mechanikákat, és ezen
alapul a konfliktusfelismerés. Observationnél lehet üres; aktív `guard` vagy
`mechanism` rekordnál legalább egy scope kötelező.

### 4.1. Evidence-típusok

| Típus | Jelentés | Generálásban használható |
|---|---|---|
| `voice_source` | Eredeti, provenance-validált saját szöveg vagy chunk | Igen, elsődleges hangforrásként |
| `mechanism` | Átvihető műfaji vagy szerkezeti döntés | Csak `active` állapotban |
| `guard` | Tiltás, hard release check vagy puha ellenőrzési szempont | Csak `active` állapotban |
| `evaluation_observation` | Emberi összevetés és indoklás auditrekordja | Nem, csak kurálási bemenetként |
| `utility_observation` | Forrásszintű, elfogadáshoz kötött utility | Csak a meglévő küszöb és zsugorítás után |

### 4.2. Autoritás

Az `authority` azt jelzi, mire jogosít a rekord:

- `voice`: saját hang és lokális stílusmechanika;
- `genre_mechanism`: műfaji kompozíciós vagy előadásmódbeli döntés;
- `generation_guard`: generálás vagy release ellenőrzési korlát;
- `evaluation_only`: audit- és kurálási evidence, közvetlen generálási hatás nélkül;
- `utility_only`: kizárólag a meglévő, küszöbölt utility-reranker bemenete.

Az autoritási sorrend: provenance-validált `voice_source` > aktív, kurált
műfaji evidence > aggregált dialóguskalibráció > globális heurisztika. Az
evaluation observation soha nem írhat felül közvetlen saját forrást.

### 4.3. Státusz és kurátori döntés

Derived rekord induló státusza `pending_review`. Engedélyezett átmenetek:

- `pending_review -> active`;
- `pending_review -> rejected`;
- `active -> retired`;
- `active -> active`, ha új decision rekord csak indoklást vagy confidence-et
  pontosít, és nem változtatja meg az evidence tartalmát.

`rejected` és `retired` rekord nem aktiválható újra helyben. Új értelmezéshez
új evidence-rekord készül, amely `supersedes` alatt hivatkozik a régire. Minden
döntés tartalmazza az evidence ID-t, az új státuszt, a döntési indokot, az
időbélyeget és a `curator: "peter"` értéket. Az első verzió egyszemélyes, ezért
nincs felhasználó- vagy jogosultságkezelés.

## 5. Vaktesztimport

A finalizált `human-test-result.json` minden tétele pontosan egy
`evaluation_observation` rekordot hoz létre. A `content` megőrzi:

- a választott rendszert vagy döntetlent;
- az emberi indokot;
- az általános megjegyzést;
- a flag-eket;
- a két jelölt kiemelését és jegyzetét;
- a két draft SHA-256 hashét, a finalizált feloldás után rendszer szerint
  (`engine_v3`, `legacy`) kulcsolva.

Nem kerül bele a draftok teljes szövege, bal/jobb pozíciója vagy a privát vak
mapping. A `chosen_system` megtartható, mert a teszt már finalizált és az
elemzéshez szükséges; közvetlen generálási autoritást ettől nem kap.

Az `evidence_id` a sémaazonosító, source run ID, item ID, brief ID és a
normalizált content kanonikus SHA-256 hashéből származik. Azonos input ismételt
importja nulla új rekordot ír. Ütköző azonosító eltérő tartalommal hard error.

Az import nem írja a `retrieval-utility.jsonl` vagy `voice-feedback.jsonl`
fájlt, és nem módosítja a finalizált teszteredményt.

## 6. Kurált aktiválás

A kurátor az observation alapján három dolgot tehet:

1. elutasítja mint nem általánosítható vagy félreérthető jelet;
2. új `guard` rekordot hoz létre;
3. új `mechanism` rekordot hoz létre.

Az observation maga egyik esetben sem válik generálási inputtá. Az új rekord
`provenance.parent_evidence_ids` alatt visszahivatkozik az összes alátámasztó
observationre. Egyetlen világos, konkrét emberi indok elegendő lehet alacsony
vagy közepes confidence-ű guardhoz, de széles, globális preferenciához több
független observation szükséges. A puszta műfaji nyerési arány nem aktiválható
mechanikaként.

Az első kurálási kör csak konkrét, végrehajtható szabályt aktivál. Példák:

- ne használja a „méltányos ellenérv/ellenpont” fordulatot kész formulaként;
- Markdown címsor csak azt támogató célfelületen jelenjen meg;
- slamnél legyen egyszeri hallhatóság és előadói ív;
- reklámnál az első evidens koncepciót kötelezően vizsgálja felül;
- dalszövegnél az énekelhetőség, hangsúly és refrénfunkció hard ellenőrzés.

Ezek pontos szövege és confidence-e az observationök tételes kurálásakor
születik meg; a design nem nyilvánítja őket automatikusan tanult preferenciává.

## 7. Selector

A selector bemenete:

- brief-plan: brief, műfaj, közönség, cél, hangtengelyek és tiltások;
- a jelenlegi RAG-portfólió;
- az evidence és decision ledger aktuális állapota;
- a verziózott selection policy;
- opcionálisan a meglévő retrieval utility ledger.

A kimenet négy elkülönített sáv:

1. `voice`: 3–5 releváns saját execution source a jelenlegi content/style
   retrievalből;
2. `mechanisms`: legfeljebb 3 aktív, brief- és műfajreleváns mechanika;
3. `guards`: minden releváns hard guard és legfeljebb 3 soft guard;
4. `utility`: csak a meglévő minimum műfajazonos megfigyelés után alkalmazott,
   zsugorított forrásszintű módosítás.

### 7.1. Statikus selection score

A derived evidence determinisztikus pontszáma:

```text
brief_fit + genre_fit + authority_weight + confidence_weight + specificity
```

A súlyok a verziózott `evidence-policy.json` fájlban vannak. Ez kézi policy,
nem tanult preference. Azonos pontnál az `evidence_id` szerinti rendezés ad
reprodukálható eredményt. A globális rekord gyengébb egy azonos minőségű,
műfajspecifikus rekordnál.

### 7.2. Konfliktus

Két aktív rekord konfliktus, ha ugyanarra a normalizált scope-ra ellentétes
direktívát ad, és egyik sem `supersedes` kapcsolatban áll a másikkal. A
selector mindkettőt kihagyja az aktív packetből, és `conflicts` alatt jelzi az
ID-ket és a scope-ot. Nem választ csendben frissebb vagy magasabb confidence-ű
rekordot.

### 7.3. Fallback

Ha nincs derived ledger vagy nincs releváns aktív rekord, az Engine jelenlegi
retrievalje változatlanul működik. `low` retrieval confidence mellett az
`abstain_from_voice_claim` megmarad. Hiányos vagy hibás ledger hard hibát okoz
az explicit kurátori/import CLI-ben, de Engine-futtatáskor biztonságos
diagnosztikával kihagyja a derived réteget, és nem ad részben valid evidence-t.

## 8. Engine packet és kompatibilitás

Az Engine új packet-sémája `mind-vault-engine-packet/v2`. Megőrzi a jelenlegi
`brief_plan`, `retrieval`, `channels`, `preference_reranker`,
`evidence_compiler` és `source_trace` mezőket, és hozzáadja:

- `evidence_policy`: policy-verzió, ledger hash és
  `manual_policy_cold_start` állapot;
- `selected_evidence`: a voice, mechanism és guard sáv;
- `selection_trace`: pontszámok és beválasztási/kihagyási indokok;
- `conflicts`: feloldatlan aktív evidence-konfliktusok.

A `preference_reranker` külön komponens marad. Derived guard vagy mechanism
nem növeli a `utility_weighted_sources` számlálót, és nem változtatja az
állapotát `observed` értékre.

A `generation_critique_workflow.py` az átmenetben v1 és v2 packetet is fogad.
V1-nél a jelenlegi működést, v2-nél az új sávokat és trace-t őrzi meg. Meglévő
publikus/private vakítási és SHA-kötési garanciáit nem gyengítheti.

## 9. Fájlhatárok

Tervezett új fájlok:

- `skills/peter-irta/scripts/evidence_vault.py` — séma, kanonikus hash,
  ledgerbetöltés, állapotképzés és selector;
- `skills/peter-irta/scripts/import_human_blind_feedback.py` — immutable
  vaktesztimport;
- `skills/peter-irta/scripts/curate_evidence.py` — listázás, létrehozás,
  aktiválás, elutasítás és nyugdíjazás;
- `skills/peter-irta/references/evidence-policy.json` — verziózott statikus
  selection policy;
- `skills/peter-irta/tests/test_evidence_vault.py` — új egységtesztek.

Tervezett módosítások:

- `skills/peter-irta/scripts/mind_vault_engine.py`;
- `skills/peter-irta/scripts/generation_critique_workflow.py`;
- közvetlenül érintett meglévő tesztek és `references/engine-v3.md`;
- a skill `SKILL.md` csak a használati szerződés szükséges pontosításával.

Runtime state:

- `skills/peter-irta/state/evidence-vault/evidence.jsonl`;
- `skills/peter-irta/state/evidence-vault/decisions.jsonl`.

A state továbbra is lokális és gitignore-olt. Tesztfixture nem hivatkozhat az
élő ledgerre.

## 10. Első implementációs egység

Az első coherent vertical slice:

1. evidence-séma és determinisztikus ID;
2. a finalizált 30-as vakteszt idempotens importja `pending_review` állapotba;
3. CLI-alapú kurátori döntések és derived guard/mechanism létrehozás;
4. determinisztikus selector;
5. Engine packet v2 integráció, v1 workflow-kompatibilitással;
6. a jóváhagyott első guard/mechanism készlet kézi aktiválása;
7. célzott és teljes skill-validáció.

Nem része ennek az egységnek új generáció vagy új vakteszt. Az csak a selector
és guardok validálása után, külön mérési egységként készül.

## 11. Tesztstratégia

Kötelező automatikus ellenőrzések:

- séma és enumok validálása;
- 30 egyedi observation és 10 x 3 műfaji lefedettség;
- azonos import másodszor nulla új rekordot ír;
- módosított input/hash vagy ID-ütközés hard error;
- nincs teljes draftszöveg, bal/jobb pozíció vagy privát mapping a ledgerben;
- csak engedélyezett státuszátmenet fogadható el;
- minden aktív derived rekordnak van kurátori indoka és parent evidence-e;
- selector determinisztikus azonos brief, policy és ledger mellett;
- műfajspecifikus evidence előzi az azonos minőségű globálist;
- hard guardok nem vesznek el a soft limit miatt;
- konfliktusos evidence nem kerül execution packetbe;
- derived evidence nem kapcsolja ki a reranker cold-start állapotát;
- v1 és v2 generation-critique input egyaránt elfogadott;
- régi Engine működés marad, ha derived state nincs;
- teljes `peter-irta` suite, Python `py_compile`, skill validator és
  `git diff --check` sikeres.

## 12. Elfogadási feltételek

Az egység akkor kész, ha:

1. a 30-as vakteszt reprodukálhatóan, adatvesztés nélkül importálható;
2. egyetlen importált observation sem befolyásol generálást kurátori döntés
   nélkül;
3. az első kézzel jóváhagyott guardok és mechanikák megjelennek a releváns
   Engine packetben, irreleváns műfajban nem;
4. a packet trace-ből minden beválasztás és kihagyás megmagyarázható;
5. a reranker továbbra is őszintén cold-start, amíg nincs elegendő valódi
   utility-adat;
6. nincs RAG rebuild, release, deploy vagy MCP-adapter;
7. a dirty worktree minden unrelated változása érintetlen.
