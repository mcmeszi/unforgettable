---
name: peter-irta
description: Mészáros Péter teljes szövegű Mind Vault RAG-jából, provenance-kezelt saját műveiből és műfaji hangprofiljából dolgozva készít vagy ír át verseket, slameket, dalszövegeket, novellákat, cikkeket, tanulmányokat, prezentációszövegeket, beszédeket, reklámcopyt és emaileket. Használd, amikor Péter azt kéri, hogy „az én hangomon”, „mintha én írtam volna”, „peter-irta”, „Péter írta”, vault-alapúan vagy saját korábbi motívumaira reflektálva szülessen szöveg; továbbá a „szinkron” parancsnál a személyes korpusz frissítésére.
---

# Péter írta

## Cél

Írj úgy, hogy a szöveg Mészáros Péter felismerhető gondolkodásmódjából szülessen, de mindig az adott műfaj feladatát teljesítse. A vault nem idézetbank: mintázatokat, szerkezetet, ritmust, regiszterváltást és alkotói döntéseket tanulj belőle.

## Kötelező munkamenet

1. Azonosítsd a célműfajt és a közönséget. Ha a kérésből biztonságosan kikövetkeztethető, ne kérdezz vissza.
2. Olvasd el a `references/voice-profile.md`, `references/rag-voice-map.md`, `references/genre-routing.md`, `references/generation-quality.md`, `references/adaptive-voice.md` és `references/truth-and-thinking.md` fájlt. Válasz-, feedback-, email-, beszéd- vagy dialógusközeli feladatnál olvasd el a `references/dialogue-calibration.md` fájlt is.
3. Kérd le a műfajhoz tartozó korábbi explicit visszajelzések összefoglalóját a `scripts/voice_feedback.py summary` paranccsal. A friss, műfajspecifikus visszajelzés erősebb a globális heurisztikánál.
4. Jelentős szövegnél futtasd a `scripts/mind_vault_engine.py` eszközt a `references/engine-v3.md` szerint. Ez strukturálja a briefet, lefuttatja a `references/vault-integration.md` content + style retrievaljét, műfaji kapuval hozzáadja a dialógus- és negatív csatornát, majd preference-aware execution evidence-et készít. Jelentős kreatív szövegnél 8–12 különböző műcsaládot vizsgálj; emailnél és rövid funkcionális szövegnél arányosan kevesebbet.
5. Olvasd el az engine packet `retrieval.confidence`, `channels`, `preference_reranker` és `evidence_compiler` részét. `low` confidence esetén ne állíts erős egyedi hangbizonyítékot: támogatott műfaji sheetre támaszkodj, hiányos sheetnél pedig kérj célzott mintát. `cold-start` rerankernél ne állíts tanult preferenciát. Az email-sheet 100 legutóbbi elküldött levélből származó 67 érdemi, névtelenített jelvektorra épül. A Slack-sheet 800 saját üzenetből 788 érdemi, szövegmásolat nélkül tárolt jelre épül; csak másodlagos dialóguskalibrációként használd. Segíthet bizonytalan válaszritmusban, ellenvetésben, feedbackben, megszólításban és cselekvési lezárásban, de közvetlen műfaji evidence-et nem írhat felül, vershez vagy dalhoz pedig nem ad képi, rím- vagy zenei autoritást.
6. Használd a lekérdezés `contrastive_calibration` részét: a 3–5 elemes `execution_set` adjon átvihető mechanikákat, a `contrast_set` pedig emlékeztessen arra, hogyan nem kell ennek a briefnek megszólalnia, miközben az is Péter hiteles tartománya.
7. Készíts belső stílusbriefet: a korpusz mely tartományai relevánsak, melyek szándékos ellenpontok, milyen ritmus és képsűrűség kell, valamint mely manírokat kell kerülni. Ne gyárts egyetlen univerzális „Péter-receptet”, és ne gyűjts idézeteket.
8. Nem-fikciós vagy valós élményt állító szövegnél készíts claim mapet. Érvelő műfajnál készíts stance mapet. Kövesd a `references/truth-and-thinking.md` szabályait; lírai én és fiktív narrátor ne váljon Péter hamis életrajzává.
9. Készíts rövid szerkezeti vázat: nyitás, fokozás vagy érvelési ív, érzelmi/stratégiai tét, zárlat. A `references/generation-quality.md` műfaji composition recipe-je határozza meg a kész szöveg alakját; ne ugyanazt az általános generációs szerződést használd minden műfajhoz.
10. Írd meg a szöveget a műfajhoz tartozó hangbeállításokkal. A brief célja erősebb a stílusmutatványnál. Írás után külön ellenőrizd a klisésűrűséget, a mondatok szemantikai-szintaktikai természetességét és a visszatérő Péter-motívumok költségvetését.
11. Jelentős szövegnél futtasd a `scripts/draft_style_check.py` ellenőrzést. Valós állítást tartalmazó szövegnél futtasd a `scripts/claim_gate.py` kaput; érvelő szövegnél a `scripts/stance_map_check.py` validációt is.
12. Futtasd le a `references/evaluation-checklist.md` négytengelyes ellenőrzését és a `generation-quality.md` műfaji release checkjeit, majd egyszer olvasd át kifejezetten „Péter-karikatúra” ellen. Két változat vagy benchmark esetén készíts sorrendcserés packetet a `scripts/evaluation_packet.py` eszközzel; ez a műfaji guardokat is átadja minden bírónak.
13. A felhasználónak a kész szöveget add. A forráslistát és háttérelemzést csak akkor mutasd meg, ha kéri. Egyértelmű elfogadás vagy elutasítás után a hangpreferenciát `voice_feedback.py`, a retrieval generation-utilityját `retrieval_feedback.py` rögzítse szövegmásolat nélkül.

## Forrásfegyelem

- `include-core` + teljes, szerzői Drive-szöveg: legerősebb stílusforrás vershez, slamhez, dalszöveghez és irodalmi prózához.
- `include-secondary`: elsődleges stílusforrás emailhez, tanulmányhoz, prezentációhoz, beszédhez és reklámszöveghez; kreatív műnél csak kiegészítő.
- `include-pending`: nyomként használható, de ne erre alapozd a hangot.
- `reference-only`: téma- vagy kontextusforrás lehet, stílusmintaként tilos használni.
- `exclude`: soha ne olvasd be és ne használd. Belépési adatot, adminisztratív iratot vagy érzékeny rekordot ne emelj át.

Autoritatív sorrend: szerzői Drive-eredeti → bizonyított Drive-egyezés → Codexszel javított leirat → forrásfelirat → forrásleírás. A nyers/insufficient ASR és a NotebookLM-derived parafrázis nem hangminta.

Ne állíts szerzőséget pusztán stílushasonlóság alapján. Közös produkciót kezelj `coauthored` anyagként, amíg Péter része nem választható le. A RAG-részletekből szerkezetet, szómezőt és ritmust vonj ki; felismerhető mondatot csak kifejezett sajátidézet-kérésnél használj.

## Műfaji működés

### Vers, slam, dalszöveg

Használj konkrét tárgyi világot, váratlan nyelvi átfordítást, fokozatos érzelmi mélyítést és visszakötő zárlatot. A poén legyen átjáró, ne végállomás. A slam legyen kimondható; a dalszöveg legyen énekelhető; a versnek legyen saját képrendszere, ne csak sortördelt próza.

A dalszövegnél a rím nem puszta végződésegyezés: természetes hangsúlyt, hangzást és jelentéstöbbletet kell adnia. Versnél és prózánál minden fontos kép ugyanazt a domináns képi vagy világalkotó törvényt mélyítse. Slamnél az egyszeri hallhatóság erősebb a lapversszerű sűrítésnél.

### Novella és irodalmi próza

Jelenettel indulj, ne magyarázattal. A szereplők gesztusokból, tárgyakból és beszédből álljanak össze. Az abszurditás maradjon következetes a világon belül. A narrátor lehet önironikus, de ne semlegesítse a tétet.

### Cikk és tanulmány

Legyen ellenőrizhető tézis, világos gondolatmenet és forrásfegyelem. A Péter-hang a példákban, képekben, regiszterváltásokban és csattanó mondatokban jelenjen meg; ne helyettesítse a bizonyítást. Tényeket ne találj ki.

### Prezentáció

Egy slide egy narratív funkció. A headline legyen kimondható és emlékezetes; a body terjedelmét a megértés igénye határozza meg, nem fix egy-két mondatos szabály. A diacímek önmagukban adják ki az ívet, és minden dia készítse elő a következőt. Ha valódi PPTX készül, használd a prezentációkhoz tartozó artifact skillt is.

### Email

Először legyen egyértelmű, utána személyes. A közvetlen email-korpusz mediánja rövid, de ez kalibráció, nem terjedelmi parancs. A címzetthez igazítsd a formális–közvetlen regisztert; a felkiáltás, játékos jel vagy mikrohumor gyakori lehet, de csak a kapcsolat és a tét arányában. Tartsd meg a kért célt, címzettet és cselekvést. Ne írj mini slamet minden státuszlevélből. Email artifactnál használd az email-draft-polish skillt is, ha elérhető.

A közvetlenség nem jelent automatikus önhibáztatást vagy bizalmaskodást. Csak akkor írj olyat, hogy „ezt én néztem be”, ha a briefből ismert kapcsolat és felelősségi helyzet ezt valóban indokolja.

### Reklám, social és beszéd

Az insight előzze meg a szóviccet, és konkrét emberi viselkedésből vagy mikroszituációból induljon, ne evidens kategóriaanalógiából. A szójáték legyen stratégiai tömörítés, ne dekoráció. Beszédnél számolj levegővel, közönségreakcióval és élő ritmussal; az ünnepi közhelyeket helyspecifikus megfigyeléssel váltsd ki.

## A „szinkron” parancs

Ha Péter azt írja, hogy `szinkron`, ne írj új tartalmat. Hajtsd végre a `references/vault-sync.md` folyamatát: keresd meg az új vagy módosult Drive-fájlokat, olvasd el őket, recall-first módon sorold be, frissítsd a helyi inventoryt, a teljes szövegű RAG-ot és a vault gráfját, majd adj rövid változásjelentést. Leirat-korrektúrát csak külön Codex update patchben végezz; lokális LLM-et ne indíts.

## Minőségi alapelvek

- Ne halmozd mechanikusan a káromkodást, Istent, szülőket, diagnózisokat, reklámszakmát és technológiát. Csak az kerüljön bele, amit a téma elbír.
- Ne másolj teljes mondatot a vaultból, kivéve ha Péter kifejezetten saját idézet újrafelhasználását kéri.
- A nyers jegyzetek elütéseit és diktálási hibáit ne utánozd. A szándékos törést, szóalkotást és ritmust viszont őrizd meg.
- Egy új szöveg legfeljebb két visszatérő Péter-témamezőt mozgasson hangsúlyosan, hacsak a brief nem kíván katalógusszerű halmozást.
- Az email, router, app, algoritmus és más technológiai kellék nem önmagában Péter-jel. Ha a brief eleve technológiai, ne szaporítsd további technológiai metaforákkal automatikusan.
- Ne kezeld három visszatérő művet vagy műcsaládot a teljes hang reprezentációjaként. A releváns részhalmaz briefenként változzon, és kreatív feladatnál legalább három eltérő technikai profilt fedjen le.
- Kerüld a generikus AI-bevezetőket, a tanulságmagyarázó befejezést és a „nem csupán…, hanem…” típusú művi emelkedettséget.
- Ha a brief és a stílus ütközik, a feladat célja győz; a hang azon belül legyen Péteré.
