# Adaptív hangkalibráció

## 1. Kontrasztív példák

A pozitív példa önmagában könnyen manírrá válik. A `vault_query.py` ezért két készletet ad:

- `execution_set`: 3–5, a brief hangtengelyeihez közeli saját mű. Forrásonként legfeljebb egy szerkezeti vagy ritmikai döntést vigyél tovább.
- `contrast_set`: két távoli, de hiteles Péter-mű. Ne utánozd őket ebben a draftban; arra szolgálnak, hogy a skill ne tévessze össze Péter teljes hangját az aktuális móddal.

Ez nem jó/rossz felosztás. Ugyanaz a mű más briefnél átkerülhet az execution setbe.

## 2. Ritmusujjlenyomat

A lekérdező minden teljes forrásszövegből mér többek között mondathosszt, mondathossz-ingadozást, rövid és hosszú mondatok arányát, kérdés- és felkiáltássűrűséget, sortöréssűrűséget, első és második személyt, valamint lexikai változatosságot.

A `style_fingerprint.metric_bands` kizárólag az aktuális execution setből készül. Ne használd szerzőségvizsgálatra, és ne kezeld kötelező kvótának. Arra jó, hogy észrevedd például: a draft véletlenül túl egyenletes, túl magyarázó vagy túl kevéssé személyes lett a választott Péter-tartományhoz képest.

```powershell
python -X utf8 scripts/draft_style_check.py --portfolio "portfolio.json" --draft "draft.md"
```

## 3. Explicit visszacsatolás

Írás előtt kérd le a műfaj releváns előzményeit:

```powershell
python -X utf8 scripts/voice_feedback.py summary --genre vers
```

Ha Péter egyértelmű visszajelzést ad, rögzítsd a döntést, de ne tárold a teljes draftot. A `--draft` csak SHA-256 ujjlenyomatot ment.

```powershell
python -X utf8 scripts/voice_feedback.py record --genre vers --verdict mixed --like "a képi nyitás" --dislike "a túlmagyarázott zárlat" --directive "A zárlat maradjon nyitva" --draft "draft.md"
```

Elsőbbségi sorrend: friss műfajspecifikus explicit visszajelzés → régebbi műfajspecifikus visszajelzés → globális explicit visszajelzés → heurisztikus hangtérkép. Egyetlen reakcióból ne képezz örök szabályt; ismétlődő jelzésből alakíts preferenciát.
