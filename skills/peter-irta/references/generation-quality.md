# Műfajspecifikus generálási és kiadási szerződés

## Alapelv

A retrieval bizonyítékot ad a hanghoz, de nem garantál jó szöveget. Minden draft
egy műfajspecifikus composition recipe alapján készüljön, majd külön release
checken menjen át. A `scripts/generation_contracts.py` ennek géppel olvasható
forrása; a benchmark job és az evaluation packet ugyanazt a contractot kapja.

## Három közös release check

1. `cliche-specificity`: kész fordulat helyett van konkrét, briefből származó
   helyzet, tárgy vagy megfigyelés.
2. `syntax-semantic-coherence`: minden mondat természetes magyar mondat, és a
   hasonlat gondolati logikája első olvasásra követhető.
3. `motif-budget`: technológia, család, Isten, diagnózis, reklám és más visszatérő
   Péter-téma csak a brief által indokolt mennyiségben szerepel.

Ezeket nem lehet ritmusmetrikával kiváltani. A statisztikai style check mellett
mondatról mondatra végzett jelentésellenőrzés is kell.

## Műfaji contractok

| Műfaj | Composition recipe | Döntő release check |
|---|---|---|
| Beszéd | konkrét közönséghelyzet → szerves váltás → élő ritmus → nem közhelyes visszakötés | `live-specificity`: helyben és emberekhez szól-e? |
| Cikk | pontos tézis → érthető példa → puhító váltás → ellenpont → következmény | `tonal-balance`: a humor segíti-e az állítást? |
| Dalszöveg | érzelmi mag → új információt adó verzék → hangzásból működő refrén | `rhyme-prosody`: a rím természetes, változatos, énekelhető és jelentéshordozó-e? |
| Email | miért írok → szükséges információ → kérés → kapcsolathoz illő lezárás | `relationship-distance`: a közvetlenség nem válik-e önhibáztatássá vagy bizalmaskodássá? |
| Prezentáció | diánként egy funkció → logikai átmenet → indokolt sűrűség → cselekvés | `slide-flow`: a diacímek önmagukban kiadják-e a történetet? |
| Próza | működés közbeni jelenet → egy világalkotó szabály → fanyar humor → döntés | `image-system`: minden kép ugyanazt a világtörvényt mélyíti-e? |
| Reklám | megfigyelt viselkedés → emberi feszültség → márkabizonyíték → állítás → CTA | `behavioral-insight`: az insight konkrét mikroszituációból indul-e? |
| Slam | hallható premissza → kimondható fokozás → közönségkapcsolat → személyes lejtő → callback | `spoken-orality`: egyszeri hallásra működik-e? |
| Tanulmány | problémafelvetés → definíció → érvelő próza → ellenpont → kutatható lépés | `prose-surface`: a belső hipotézisváz olvasmányos prózává vált-e? |
| Vers | egy konkrét kép → egy képi törvény → szűkülő jelentés → lebegtető visszakötés | `image-system`: érthető és következetes-e a képrendszer? |

## Műfaji kemény hibák

- **Beszéd:** felolvasva merev, vagy a fő érzelmi állítás ünnepi közhely.
- **Cikk:** természetellenes mondatlogika, illetve a példa nem a tézist
  bizonyítja.
- **Dalszöveg:** a rím puszta toldalékegyezés, megtöri a természetes hangsúlyt,
  vagy a refrén közhelyet ismétel.
- **Email:** a kérés nem egyértelmű, vagy a hangnem közelebbinek tetteti a
  kapcsolatot a briefnél.
- **Prezentáció:** a diák felcserélhetők, illetve a tömörség miatt hiányzik a
  logikai átmenet.
- **Próza:** a képek külön hatásokként versengenek, vagy a humor megszakítja a
  jelenetet.
- **Reklám:** az insight bármely konkurenssel működne, vagy a szóvicc megelőzi a
  megfigyelést.
- **Slam:** csak visszaolvasva érthető, vagy a motívumok katalógussá válnak.
- **Tanulmány:** a belső váz minden bekezdésen látható címkévé válik.
- **Vers:** egy központi kép nem értelmezhető a vers saját világán belül, vagy a
  zárlat elmagyarázza a jelentést.

Kemény hiba esetén ne átlagolj: javítsd a draftot, majd futtasd újra a műfaji
release checket.

## Benchmark-integráció

A `prepare_generation_benchmark.py` minden publikus jobhoz hozzáadja a
`genre_quality_contract` mezőt. Az `evaluation_packet.py` ugyanezeket a guard
ID-kat adja át mindhárom bírói nézőpontnak mindkét sorrendben.

A publikus job továbbra sem tartalmazhat V1/V2 mappinget vagy valódi source ID-t.
A `private-generation-manifest.json` külön őrzi a candidate → system → retrieval
run → source ID kapcsolatot, hogy a lezárt emberi ítélet később megbízhatóan
visszaköthető legyen retrieval utilityhez. Ha a benchmark bemenete nem tartalmaz
eredeti `run_id`-t, a manifest a brief, candidate, műfaj és rendezett source ID-k
alapján stabil `benchmark-portfolio-*` ujjlenyomatot képez, és ezt a
`run_id_origin` mezőben jelzi.

A `source_linkage` pontosan azokat az `S1`–`S4` vak evidence-címkéket köti valódi
source ID-hoz, amelyeket a generátor megkapott. A teljes, de fel nem használt
retrieval-portfólió külön `portfolio_source_ids` mezőbe kerül; arra nem szabad
generation utilityt terhelni.
