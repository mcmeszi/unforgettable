# Kiadás előtti ellenőrzés

## Négy független eredménytengely

Mindegyiket külön pontozd 0–2 között; a provenance- vagy igazságkapu hibáját ne átlagold el.

1. `brief_fidelity`: tartalom, cél, terjedelem, kötelező állítások és kihagyások.
2. `genre_naturalness`: a célműfajban működik-e, nem csak stílusdemóként.
3. `author_style_match`: több külön műcsalád mechanikáihoz illeszkedik-e felismerhető mondat átvétele nélkül.
4. `originality_anti_caricature`: önálló-e, és elkerüli-e Péter motívumainak/manírjainak katalógusát.

Két változat vagy benchmark esetén futtasd a `scripts/evaluation_packet.py` eszközt. Három nézőpontot használ (`brief-editor`, `genre-practitioner`, `authorship-skeptic`), mindegyiket A/B és B/A sorrendben. A sorrenddel változó győztes instabil; a dimenziónkénti eltérést és a bírói nézetkülönbséget is őrizd meg.

A négy eredménytengely mellett kötelező a `references/generation-quality.md`
műfaji contractja. A benchmark packet a `genre_quality_contract` mezőben adja
át ugyanazokat a release checkeket minden bírónak. A műfaji kemény hibát ne
átlagold el jó briefhűséggel vagy stílusponttal.

## Részletes guardlista

Pontozd belsőleg 0–2 között. A 0 pontos elemet javítsd; a pontszámot ne mutasd meg automatikusan.

1. Pontosan teljesíti a briefet, terjedelmet és műfajt?
2. Van legalább egy konkrét, nem generikus részlet?
3. Van természetes regiszterváltás vagy gondolati csavar?
4. A humoron túl történik érzelmi vagy érvelési elmozdulás?
5. Felolvasva működik, illetve követi a műfaj tempóját?
6. A zárlat visszaköt vagy nyitva hagy, és nem magyaráz túl?
7. Nincs túl sok poén, metafora, káromkodás vagy Péter-motívum?
8. Eltűntek a generikus AI-bevezetők és töltelékmondatok?
9. Nincs kitalált tény, idegen hang vagy jogosulatlan vault-idézet?
10. Az email elküldhető, slide kivetíthető, dal énekelhető, slam kimondható?
11. A RAG-ból mechanikát vettem át, nem felismerhető mondatot vagy ritka önéletrajzi adatot?
12. Nem Péter-motívumok katalógusa lett, hanem a briefből szervesen következő saját szöveg?
13. A `[?]`-es ASR, NotebookLM-parafrázis és idegen referenciaanyag kimaradt a hangmintából?
14. Ha van műfajközi híd, tényleg új felismerést ad, és nem puszta asszociáció?
15. A forrásportfólió legalább három eltérő technikai profilt fedett le, vagy indokoltan szűkebb a feladat?
16. Nem ugyanaz a három műcsalád diktálta meg ismét a ritmust, a képeket és a zárlatot?
17. Az új szöveg a Péter-hang egy briefhez illő koordinátája, nem a teljes korpusz mesterséges átlaga?
18. Az `execution_set` mechanikái érződnek, miközben a `contrast_set` távoli formái nem szivárogtak bele reflexből?
19. A ritmusujjlenyomat eltéréseit átnéztem, de nem vasaltam a szöveget statisztikai átlagra?
20. Alkalmaztam a releváns explicit visszajelzést, és nem találtam ki olyat, amit Péter sosem mondott?
21. Minden konkrét első személyű ténynek van brief-, vault- vagy fikciós eredete, és a fikciót nem állítom Péter valódi múltjaként?
22. Érvelő műfajnál az álláspontnak van valódi tétje és méltányos ellenpontja, nem csak Péter-szókincse?
23. Nincs 12 tokenes forrásszöveg-átvétel; a 8–11 tokenes egyezéseket ellenőriztem?
24. A kész fordulatokat konkrét brief-részlet váltotta fel, és nincs kliséhalmozás?
25. Minden mondat és hasonlat természetes magyar szintaxissal, követhető gondolati logikával működik?
26. A technológiai és más visszatérő Péter-motívumok nem lépték túl a brief által indokolt szerepet?
27. A `generation-quality.md` célműfaji release checkje átment, és nincs felsorolt kemény hiba?
