# Életrajzi igazságkapu és gondolkodási DNS

## Claim map

Nem-fikciós, prezentációs, emailes, beszéd- és saját élményt állító szöveg előtt minden konkrét első személyű állítást sorolj be:

- `brief-supplied`: Péter a jelenlegi kérésben megadta.
- `vault-backed`: autoritatív saját forrás igazolja; add meg a `source_ids` listát.
- `fictional-by-genre`: lírai énhez vagy fikciós narrátorhoz tartozik, nem Péter életrajzi állítása.
- `unsupported`: nincs igazolva. Nem-fikcióban tilos a kész szövegben hagyni.

A fikciós címke nem engedély arra, hogy ritka, valódi vault-életrajzot új szereplőre másolj. A claim map JSON alakja:

```json
{"claims":[{"text":"...","label":"brief-supplied","source_ids":[]}]}
```

Ellenőrzés:

```powershell
python -X utf8 scripts/claim_gate.py --draft draft.md --portfolio portfolio.json --claim-map claim-map.json --mode nonfiction
```

Nem-fikcióban hard fail az unsupported vagy feltérképezetlen konkrét első személyű állítás. A legalább 12 normalizált tokenes vault-egyezés hard fail, kivéve külön, igazolt sajátidézet-kérésnél. A 8–11 tokenes egyezést kézzel ellenőrizd.

## Stance map

Cikkhez, tanulmányhoz, érvelő prezentációhoz, reklámstratégiához és érdemi beszédhez készíts hatmezős belső térképet:

1. `personal_stake`: miért érinti Pétert vagy a közönségét;
2. `claim`: mit állít a szöveg;
3. `not_claiming`: mit nem állít;
4. `strongest_counterargument`: az ellenoldal legerősebb, nem szalmabáb érve;
5. `where_counterargument_is_right`: hol ad neki igazat;
6. `perspective_turn`: mely konkrét megfigyelés után változik meg a nézőpont.

Mindegyik elem `brief-derived`, `vault-backed` vagy `not-applicable` eredetű. Vault-backed elemhez `source_ids` kell. Csak akkor használd az ellenérves ívet, ha valódi feszültség van; emailben vagy tisztán lírai versben ne gyárts művi vitát.

```powershell
python -X utf8 scripts/stance_map_check.py --map stance-map.json
```
