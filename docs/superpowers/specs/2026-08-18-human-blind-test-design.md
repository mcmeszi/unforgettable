# Mind Vault emberi vakteszt — design

## Cél

Készüljön egyszemélyes, helyben futó böngészős vakteszt a V1 retrieval és az
Engine v3 által generált szövegek emberi összehasonlítására. A teszt mérje a
brief teljesítését, a műfaji természetességet és a Péter-hang hitelességét úgy,
hogy a rendszerazonosság mind a harminc döntés véglegesítéséig ne jelenjen meg.

Ez egy teljes, egyszemélyes emberi benchmarkkör. Eredménye emberi evidencia, de önmagában nem tanítja a rerankert,
és nem ír automatikusan retrieval-utility vagy voice-feedback ledgert.

## Mintaválasztás

- Pontosan mind a 30 benchmark-brief kerüljön a tesztbe.
- Mind a 10 benchmark-műfajból pontosan három brief szerepeljen.
- Egy brief egyszer jelenjen meg. Fordított sorrendű ismétlés ne legyen.
- Fix, parancssorból megadható seed határozza meg a sorrendet és az oldalakat.
- Az Engine v3 pontosan 15 esetben legyen bal, 15 esetben jobb oldalon.

A public test pack csak a briefet, műfajt, két szöveget és átlátszatlan test-ID-t
tartalmazza. Nem tartalmazhat `legacy`, `engine_v3`, `A`, `B`, source-ID vagy
provenance-mapping mezőt.

## Architektúra

### 1. Preparáló

A `prepare_human_blind_test.py` explicit inputként kapja:

- a benchmark összesített eredményét;
- a 60 generált draft könyvtárát;
- a generálási jobokat vagy brief-adatokat;
- a privát rendszer blind keyt;
- a seedet és az output könyvtárat.

Kimenete három külön fájl:

- `public-test.json`: a böngészőnek átadható vak csomag;
- `private-human-key.json`: test-ID és bal/jobb pozíció rendszerazonossága.
- `human-test-manifest.json`: a két input SHA-256 értéke és a preparálási
  invariánsok összefoglalója.

A két adatfájlhoz külön SHA-256 készüljön. A private key nem kerülhet a frontend
assetjei közé és nem szolgálható ki a finalizálás előtt.

### 2. Helyi szerver

A `human_blind_test_server.py` kizárólag loopback címen induljon, külső hálózati
bind nélkül. Python standard library legyen elég; új runtime-dependency ne kelljen.

Feladatai:

- a statikus HTML/CSS/JS kiszolgálása;
- a public pack átadása;
- válaszok szerveroldali, atomikus mentése;
- hiányos válasz és korai finalizálás elutasítása;
- a private key feloldása kizárólag a 30 válasz véglegesítése után;
- az emberi benchmark eredményének JSON-exportja.

A szerver ne indítson modellhívást, ne írjon utility ledgert, és ne módosítsa a
generált draftokat vagy a gépi benchmark artifactjait.

### 3. Frontend

Egy fókuszált, editorial jellegű összehasonlító felület készüljön:

- kezdőképernyő rövid szabályokkal;
- egy brief per képernyő;
- a brief jól elkülönítve a két jelölt fölött;
- desktopon két azonos szélességű olvasóoszlop;
- keskeny kijelzőn egymás alatti szövegek, egyértelmű Bal/Jobb címkével;
- döntés: Bal / Jobb / Döntetlen;
- legalább 10 karakteres kötelező indok;
- mindkét jelölthöz opcionális „Kiemelt sor vagy megfogalmazás” mező, legfeljebb
  500 karakterrel;
- mindkét jelölthöz opcionális „Miért tetszett / mit vinnél tovább?” megjegyzés,
  legfeljebb 1500 karakterrel;
- opcionális, legfeljebb 1500 karakteres általános megjegyzés a párról;
- opcionális hibajelölések: brief-tévesztés, műfajidegenség, hamis Péter-hang,
  modorosság/karikatúra, hard-guard probléma;
- előre és vissza navigálás, mentett állapot visszatöltése;
- haladásjelző, de futás közbeni pontszám vagy rendszerutalás nélkül;
- véglegesítés előtt összefoglaló ellenőrzőképernyő;
- véglegesítés után rendszerfeloldás, 30 döntés listája és összesített eredmény.

A frontend ne használjon külső fontot, analitikát, CDN-t vagy hálózati kérést.

## Adatfolyam és állapot

1. A preparáló létrehozza és hash-eli a public packot és a private keyt.
2. A szerver betölti mindkettőt, de a frontendnek csak a public packot adja át.
3. Minden válasz — döntés, indok, hibajelölések és opcionális jelöltenkénti
   kiemelések/megjegyzések — mentése után a szerver ideiglenes fájlba ír, majd
   atomikusan lecseréli az aktív progress JSON-t.
4. A frontend frissítés vagy újraindítás után a szervertől tölti vissza az állapotot.
5. A finalizálás csak 30 érvényes döntés és indok mellett sikerül.
6. Sikeres finalizáláskor a szerver feloldja a pozíciókat, kiszámítja a
   brief-győzelmeket és kiírja a lezárt human result JSON-t.
7. Finalizált futás nem módosítható. Újrakezdéshez új run-ID és új output kell.

## Eredményformátum

A lezárt JSON tartalmazza:

- schema version, run-ID, seed és timestamp;
- public pack és private key SHA-256;
- briefenként a vak döntést, indokot, hibajelöléseket, feloldott rendszert,
  valamint rendszerhez visszakötött kiemeléseket és megjegyzéseket;
- Engine v3 / V1 / döntetlen darabszámot;
- műfajonkénti bontást;
- explicit mezőt: `utility_written=false`, `learned_preference_claimed=false`
  és `feedback_review_required=true`.

Teljes nyers draftszöveg ne kerüljön az eredményfájlba; csak draft-hash és
test-ID. Kivétel a Péter által kézzel bemásolt, legfeljebb 500 karakteres kiemelt
részlet: ez szándékos emberi feedback-evidence, nem automatikus tréningadat.

## Hibakezelés és biztonsági kapuk

- Hiányzó vagy módosult inputhash esetén a szerver ne induljon el.
- Duplikált brief, nem 30 elem, műfajonként nem három brief vagy nem 15/15
  rendszerpozíció
  preparálási hiba.
- Ismeretlen döntés, rövid indok vagy ismeretlen test-ID HTTP 400.
- Korai reveal/finalize HTTP 409.
- Nem loopback bind konfigurációs hiba.
- A `state/` output gitignore-olt maradjon; publikus PR-ba csak kód, teszt,
  referencia és üres state-placeholder kerülhet.

## Tesztelés

Automatizált tesztek fedjék le:

- a determinisztikus, mind a 30 briefet megtartó sorrendet;
- a műfajonkénti 3-as lefedettséget és a 15/15 Engine-oldal invariánst;
- a public pack rendszer- és source-ID-mentességét;
- a hash-ellenőrzést;
- az érvényes és érvénytelen answer contractot;
- a jelöltenkénti kiemelés/megjegyzés hosszkorlátját és feloldás utáni helyes
  rendszerhez kötését;
- a korai finalizálás tiltását;
- a végső feloldás és összesítés helyességét;
- azt, hogy utility és learned preference nem íródik.

Vizuális QA desktop és mobil nézetben szükséges. A fő útvonalat böngészőben végig
kell kattintani: kezdés → válaszmentés → visszatöltés → 30. döntés → finalizálás →
feloldott összesítés.

## Nem része ennek az egységnek

- több értékelő és értékelők közti egyezés;
- online hosztolás, belépés vagy megosztható publikus URL;
- automatikus utility- vagy voice-feedback írás;
- reranker-tréning vagy preference-állítás;
- újragenerálás, teljes RAG rebuild, release, deploy vagy MCP-adapter.
