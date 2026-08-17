# RAG-alapú Péter-hangtérkép

Ez a térkép a 2026. augusztus 10-i vaultból levont szerkezeti tanulság. A konkrét briefhez mindig a `scripts/vault_query.py` aktuális találatai az elsődlegesek.

## Korpuszállapot

- 368 dokumentum, ebből 327 teljes szöveg.
- 96 `include-core` alkotói forrás és 225 másodlagos szakmai/beszélt forrás.
- 43 YouTube-leirat corrected-first provenance-nel; a használhatatlan ASR nem stílusforrás.
- A NotebookLM-jegyzetek tematikus térképek, nem Péter-hangminták.

## A hang stabil mélyszerkezete

1. **Egy konkrét dolog szabályt kap.** Gyógyszer, blokk, kártya, kuka, billentyűzet, közlekedési eszköz, márka vagy adminisztratív fogalom nem díszlet, hanem a teljes szöveg működési elve.
2. **A szabály átkerül egy másik életterületre.** Technikai, vallási, reklámos, pénzügyi vagy popkulturális logika kezd el családról, intimitásról, gyászról vagy önképről beszélni.
3. **A nyelv fokozással bizonyít.** Felsorolás, variáció, kérdéssor vagy refrén ugyanazt a premisszát egyre személyesebb következményekig viszi.
4. **A beszélő saját magát is leleplezi.** Nem kívülről gúnyol; a poén visszafordul rá, ezért nem lesz fölényes stand-up.
5. **A valódi tét egyszerű mondatban érkezik.** A legsűrűbb nyelvi játék után gyakran rövidebb és csupaszabb lesz a mondat.
6. **A zárlat visszaveszi a nyitó tárgyat.** Ugyanaz a kép, kifejezés vagy közönségmozdulat tér vissza, de már más érzelmi értékkel.

## Jellegzetes transzformációk

- **Intézményi nyelv → magánélet:** adó, hitel, közbeszerzés, használati utasítás vagy kommunikációs stratégia válik érzelmi modellé.
- **Popkultúra → családi rendszer:** egy franchise vagy játékszabály segítségével válik elmondhatóvá a gyerekkor, a hatalom vagy a veszteség.
- **Technológia → hit/intimitás:** prompt, reboot, lag, interfész és algoritmus egyszerre komikus és metafizikai nyelv.
- **Test → időmérő:** légzés, pulzus, fájdalom, gyógyszerhatás vagy szexualitás méri, hogy a beszélő jelen van-e még.
- **Közhely → szó szerinti csapda:** a szöveg komolyan veszi egy szólás mechanikáját, majd addig követi, amíg személyes vagy társadalmi állítássá nem válik.

## Műfaji hangmódok

### Vers

Szűkebb képrendszer, kevesebb kiszólás, nagyobb sűrítés. A szócsavar akkor jó, ha tovább építi ugyanazt a képi törvényt. A zárlat ne mondja meg, mit kell érezni.

### Slam és beszéd

Azonnal érthető premissza; közönséghez intézett mozdulat vagy kérdés; háromlépcsős fokozás; személyes lejtő; callback. A szöveg számoljon levegővel, reakcióval és azzal, hogy egy bonyolult mondatot csak egyszer hallanak.

### Dalszöveg

Hangzásból és ismétlésből is keletkezhet jelentés. A refrén legyen egyszerűbb a verzénél, a szóalkotás énekelhető, a belső rím pedig ne rontsa el a természetes hangsúlyt.

### Próza

A tárgy vagy abszurd szabály világot szervezzen, ne csak hasonlat legyen. A sebezhetőség döntésben, gesztusban vagy következményben jelenjen meg.

### Cikk, tanulmány és prezentáció

Péter szakmai hangja diagnosztikus: pontosan megnevezi a problémát, rendszert épít köré, majd konkrét következményt mond. A humor egy tiszta címben, példában vagy váratlan összevetésben jelenjen meg; ne zavarja a bizonyíthatóságot.

### Email

Elsődleges a tisztaság és a következő lépés. A saját hangot egy természetes mondatfordulat, egy pontos kép vagy egy enyhe önirónia jelezze. Ne húzd rá a teljes slam-mechanikát.

## Mintatér, nem kánon

Ne indulj állandó címlistából. A konkrét RAG-portfólióban keresd az egymástól eltérő működéseket:

| Tartomány | Az egyik pólus | A másik pólus |
|---|---|---|
| Terjedelem és mozgás | sűrített, egy képre zárt | narratív, jeleneteken áthaladó |
| Jelentésképzés | tárgyi/képi | fogalmi, intézményi vagy interfészszerű |
| Megszólalás | lapra írt, belső | előadott, közönséghez forduló |
| Tét | intim, családi/testi | nyilvános, társadalmi/szakmai |
| Ritmus | töredezett, kihagyásos | refrénes, felsoroló vagy fokozó |

Jelentős kreatív feladatnál a portfólió legalább három különböző technikai profilt érintsen. Ezután a briefhez válassz koordinátát; ne próbáld a pólusokat mind egyetlen szövegbe zsúfolni.

## Amit ne csinálj

- Ne készíts „best of Péter” kollázst gyógyszerből, Istenből, anyából, AI-ból és káromkodásból.
- Ne emelj át ritka önéletrajzi tényt, ha a brief nem indokolja.
- Ne használd stílusmintának a NotebookLM-parafrázist, idegen referenciaanyagot vagy `[?]`-es bizonytalan ASR-részt.
- Ne tartsd kötelezőnek a humort. A Péter-hang felismerhető a pontos gondolati átfordításból is.
- Ne magyarázd el a zárlat után a szöveg jelentését.
