# Teljes szövegű Vault-integráció

## Elsődleges forrás

Add meg a RAG-gyökeret a `--rag-root` kapcsolóval vagy a
`MIND_VAULT_RAG_ROOT` környezeti változóval. Repón belüli használatnál a
`data/mind-vault/rag` és a `release/vault-final/data/mind-vault/rag` útvonalat
a lekérdező automatikusan megpróbálja.

A `scripts/vault_query.py` a `documents.json`, `chunks.json` és `connections.json` fájlokból dolgozik. Ha a workspace-réteg nem érhető el, a `release/vault-final` RAG-jára esik vissza.

A RAG 1.1-es chunkjai külön `contextual_prefix` mezőben hordozzák a műcímet, műfajt, témákat és a chunk szerepét (nyitás, középrész, zárlat). Ez részt vesz a lexikai retrievalben, de a nyers `text` változatlan marad.

## Kötelező lekérdezés

Futtasd a célműfajjal és a brief 3–6 jelentéshordozó fogalmával:

```powershell
python -X utf8 scripts/vault_query.py --genre slam --query "apa technológia halál" --variation-seed "élő közönség vallomás" --target-axis compressed_to_narrative=0.55 --target-axis image_to_conceptual=0.45 --target-axis page_to_performed=0.9 --target-axis intimate_to_public=0.35 --chunks-per-source 3 --bridge-limit 3
```

A lekérdező:

- műfajfüggő méretű portfóliót épít: jelentős kreatív szövegnél alapból 10, szakmai szövegnél 7, emailnél 5 műcsaládot;
- relevancia mellett technikai, tematikus, terjedelmi és előadásmódbeli újdonságot is jutalmaz;
- teljes RAG-chunkokat ad, nem puszta címlistát;
- canonical cím, szöveghash és forrásútvonal alapján deduplikál;
- kizárja a `reference-only`, metadata-only, NotebookLM-derived, raw és insufficient ASR-forrásokat;
- jelzi a `[?]`-es bizonytalan corrected-ASR részleteket;
- eltérő műfajú kapcsolatokat is ad lehetséges gondolati hídként.
- minden forráshoz heurisztikus `mode`, `technique_tags` és `range_axes` mezőt ad. Ezek mintaválasztási segédletek, nem irodalomtudományi tényállítások.
- külön BM25-szerű `content_score` és hangtengely/profil alapú `style_score` rangsort készít, majd reciprocal rank fusionnel képez `fused_score` értéket;
- a megadott brief-koordinátához 3–5 közeli `execution_set` mintát és két távoli `contrast_set` ellenpontot ad;
- az execution set teljes szövegeiből műfaj- és briefspecifikus `style_fingerprint` ritmussávokat számol.
- külön `content` és `style` csatornán választ forrásokat: a tartalmi anchorok a brief jelentéséhez, a stílus-anchorok a műfaji módhoz és a megadott hangtengelyekhez igazodnak;
- a stílus-anchoroknál a target-fit mellett külön jutalmazza az új működésmódot és technikai profilt, hogy a style-csatorna ne szűküljön egyetlen közeli hangváltozatra;
- minden forrásnál külön közli a `content_score`, `style_score`, `retrieval_channel` és korábbi elfogadásokból tanult `utility_weight` értéket.
- `retrieval_confidence` alatt jelzi a portfólió teljességét, az azonos műfajú és elsődleges források arányát, valamint hogy szabad-e erős hangállítást tenni;
- `author_writing_sheet` alatt átadja a korpuszból generált műfaji sávokat, karikatúra-guardot és — ha elérhető — a műfajra korlátozott `dialogue_support` Slack-kalibrációt. A `supported`, `adjacent`, `insufficient` és `missing` szinteket szó szerint kezeld.

## Confidence-kapu

- `high`: a portfólió és a sheet együtt erős, briefspecifikus hangbizonyíték.
- `medium`: írj, de a kevésbé stabil stílusjeleket ne kezeld kötelező sajátosságként.
- `low`: `abstain_from_voice_claim=true`; támogatott sheet esetén abból és óvatos helyi evidence-ből dolgozz, különben kérj célzott mintát.
- A tanulmány-sheet jelenleg kevés közvetlen műcsalád miatt lehet `insufficient`. Az email-sheet közvetlen, névtelenített Gmail-jelvektorokra épül; a nyers levelek nincsenek tárolva. A Slack `dialogue_support` kizárólag másodlagos válasz- és párbeszédmechanikai bizonyíték: a közvetlen műfaji forrást nem írhatja felül, versnél és dalszövegnél csak konkrét dialógusrészletre használható.

## Generation-utility visszajelzés

Ha Péter egy elkészült szöveget egyértelműen elfogad vagy elutasít, a használt
portfólió hasznossága külön, szövegmásolat nélkül rögzíthető:

```powershell
python -X utf8 scripts/retrieval_feedback.py --portfolio portfolio.json --utility 1 --note "elfogadott első változat"
```

Az érték `1` (hasznos), `0` (semleges) vagy `-1` (káros) lehet. Opcionálisan a négy értékelési dimenzió is megadható ismételt `--dimension nev=0..2` kapcsolóval. Egy forrás csak legalább három műfajazonos megfigyelés után kap zsugorított, legfeljebb kis súlyú módosítást. Visszajelzés nélkül a rendszer változatlanul működik.

## Kétlépcsős hangtérkép

1. **Tartományfeltárás:** olvasd át a teljes portfólió evidence-részleteit. Keresd a távolságokat: sűrített ↔ narratív; képi ↔ fogalmi/interfészszerű; lapra írt ↔ előadott; intim ↔ nyilvános/társadalmi. Ne átlagold őket egyetlen hanggá.
2. **Brief-koordináta:** döntsd el, az új szöveg hol áll ezeken a tengelyeken, és add át ismételt `--target-axis tengely=0..1` kapcsolókkal. A program választja ki a közeli kivitelezési mintákat és a távoli ellenpontokat.
3. **Mechanikakivonás:** minden kiválasztott forrásból legfeljebb egy átvihető döntést vegyél át. Egyik mű se váljon receptté.
4. **Beszélgetési változatosság:** ha ugyanabban a beszélgetésben újabb hasonló szöveg készül, a korábban domináns címeket add át ismételt `--exclude-family "Cím"` kapcsolókkal. Legfeljebb a portfólió harmada ismétlődjön, kivéve ha Péter kifejezetten ugyanahhoz a műhöz akar visszanyúlni.

A `--variation-seed` ne véletlen számsor legyen, hanem a brief formája, közönsége és tónusa 2–4 szóban. Ez a közel azonos relevanciájú műcsaládokat forgatja, miközben a lekérdezés reprodukálható marad.

## Belső feldolgozás

1. Ne a találati lista első három címéből írj. Előbb térképezd fel az egész portfóliót, majd jelöld ki a briefhez tartozó 3–5 kivitelezési mintát és az ellenpontokat.
2. A `[?]`-es evidence-részt ne használd szó- vagy mondatmintának.
3. Jegyezd fel a releváns tartományt, majd forrásonként legfeljebb egy mechanikát: például tárgyi szabály, fokozási forma, komikus–érzelmi csuklópont, képsűrűség vagy mondathossz.
4. Válassz egyetlen műfajközi hidat, ha az érdemben gazdagítja a briefet. Ne erőltesd a RAG által jelzett kapcsolatot.
5. Zárd be a forrásszövegeket, és a mechanikákból írj új, briefspecifikus szöveget.
6. Ha a felhasználó saját idézetet kér, külön keresd vissza és jelöld idézetként; egyébként ne emelj át felismerhető mondatot.
7. Jelentős draft után futtasd: `python -X utf8 scripts/draft_style_check.py --portfolio portfolio.json --draft draft.md`. Az eltérés nem automatikus hiba: vizsgáld meg, hogy indokolt műfaji döntés vagy véletlen AI-egyenletesítés okozza-e.

## Forrásarány műfaj szerint

- Vers/slam/dal/próza: a portfólió többsége `include-core` szerzői Drive legyen, de fedjen le legalább három eltérő technikai profilt. Corrected előadás ritmusforrás, szakmai vagy interjús szöveg gondolati ellenpont lehet.
- Cikk/tanulmány/prezentáció/reklám: a szakmai források domináljanak, mellé saját interjú/beszéd és indokolt esetben kreatív ellenpont kerüljön.
- Email: 4–5 releváns szakmai minta elég; kreatív híd csak akkor kell, ha a címzett vagy a cél elbírja.

Ha a RAG nem érhető el, használd a `voice-profile.md`, `rag-voice-map.md` és `genre-routing.md` fájlokat. Csak akkor jelezd a korlátozást, ha Péter konkrét korábbi műre vagy saját idézetre hivatkozik.
