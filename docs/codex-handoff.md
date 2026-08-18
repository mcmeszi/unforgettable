# Codex handoff — Mind Vault emberi vakteszt

Frissítve: 2026-08-18

## Cél és aktuális mérföldkő

A 30 briefes V1 retrieval vs Engine v3 emberi vakteszt teljes helyi alkalmazása
elkészült és Task 5 böngészős QA-n átment. A valós, gitignore-olt 30-as pack
érintetlen; Péter fő futása friss, 0/30 válaszos és nincs finalizálva. A helyi
szerver kizárólag `127.0.0.1:8766` címen fut.

## Azonnali használat

Nyisd meg:

`http://127.0.0.1:8766/`

Ha a szervert később újra kell indítani, ez a checkouttól független, önálló
PowerShell-parancs:

```powershell
& 'C:\Users\Mészáros Péter\AppData\Local\Programs\Python\Python312\python.exe' 'C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\scripts\human_blind_test_server.py' --public 'C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\public-test.json' --private 'C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\private-human-key.json' --manifest 'C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\human-test-manifest.json' --progress 'C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\human-test-progress.json' --result 'C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\human-test-result.json' --host 127.0.0.1 --port 8766
```

Indítás előtt ellenőrizd, hogy a 8766-os porton nem fut már ugyanez a folyamat;
egyidejűleg csak egy szerver írhatja ezt a progress/result párt.

## Valós pack és mentési viselkedés

- Pack könyvtár:
  `C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\`
- Public pack: `public-test.json`
- Privát feloldókulcs: `private-human-key.json`
- Manifest: `human-test-manifest.json`
- Seed: `20260818`
- Manifest public canonical SHA-256:
  `ff3b285302f2ea9cd8aa4cac664804872751fe4b724e9f83e60a8452f9fa83c4`
- Manifest private canonical SHA-256:
  `3a9e68c51236cf8eb01620b2b8e69b769b7b1d19919a6ef1db52b49fc0239f11`
- Minden `Mentés és tovább` kérés az összes választott és opcionális mezőt
  `/api/answer` útvonalon menti. A szerver ideiglenes fájlt ír, majd atomi
  cserével frissíti a progress JSON-t.
- Reload/újraindítás után a kliens `/api/progress` útvonalról visszatölti a
  mentett döntést, indokot, flag-eket, mindkét jelölt kiemelését/jegyzetét és az
  általános megjegyzést.
- Fő progress útvonal:
  `C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\human-test-progress.json`
- Végső eredmény útvonal:
  `C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\human-test-result.json`
- Finalizálás csak 30 érvényes válasznál lehetséges. Utána az eredmény
  immutable; minden további answer write HTTP 409.
- QA utáni fő állapot: `answered_count=0`, `finalized=false`; a fő progress- és
  result-fájl jelenleg nem létezik.

## Kiválasztott briefek tesztsorrendben

1. `proza-03`
2. `vers-03`
3. `beszed-03`
4. `cikk-03`
5. `tanulmany-03`
6. `prezentacio-02`
7. `tanulmany-01`
8. `reklam-01`
9. `prezentacio-01`
10. `slam-02`
11. `cikk-02`
12. `beszed-01`
13. `beszed-02`
14. `reklam-03`
15. `vers-02`
16. `dalszoveg-03`
17. `tanulmany-02`
18. `email-03`
19. `proza-01`
20. `slam-03`
21. `email-01`
22. `slam-01`
23. `proza-02`
24. `vers-01`
25. `dalszoveg-01`
26. `dalszoveg-02`
27. `prezentacio-03`
28. `reklam-02`
29. `cikk-01`
30. `email-02`

## Task 5 QA és javítás

- A teljes fő útvonal valódi böngészőben futott: start, teljes első feedback,
  mentés, reload, Back, 30/30 review, finalizálás, reveal és második írás
  elutasítása.
- Az első tételben egyedi Bal/Jobb kiemelések és jegyzetek kerültek a disposable
  futásba. A privát kulcs alapján Bal=`engine_v3`, Jobb=`legacy`; a lezárt
  eredmény mindkét feedbacket a helyes rendszerhez kötötte.
- A második írás HTTP 409-et adott: `test has already been finalized`.
- Talált és javított UI-hiba: a programmatikusan fókuszált view-címeken Chromium
  alapértelmezett fekete focus-keretet rajzolt. Regressziós teszt készült, a
  heading outline megszűnt, az aktív fókuszcél és az interaktív vezérlők
  oxblood focus-jelzése megmaradt.
- Desktop mérés: 1536×1024 viewport, két 768 px-es azonos oszlop, nincs
  vízszintes overflow.
- Mobil mérés: 390×844 viewport, Bal → Jobb sorrend, mindkettő 390 px, nincs
  vízszintes overflow.
- Böngészőkonzol: 0 error, 0 warning.

Disposable bizonyítékok:

- Progress:
  `.superpowers\sdd\2026-08-18-human-blind-test\task-5-disposable-run\human-test-progress.json`
- Final result:
  `.superpowers\sdd\2026-08-18-human-blind-test\task-5-disposable-run\human-test-result.json`
- Disposable result SHA-256:
  `57B7F42E76F2C9FC3DBB6115DFB42E1E42F5E16F08474BC5FEECF63E130DCFF0`
- QA riport:
  `.superpowers\sdd\2026-08-18-human-blind-test\task-5-report.md`
- Pontos viewport bizonyíték:
  `.superpowers\sdd\2026-08-18-human-blind-test\task-5-visual-evidence.json`
- Finalizált DOM/console bizonyíték:
  `.superpowers\sdd\2026-08-18-human-blind-test\task-5-browser-evidence.json`
- Fő képek: `task-5-start-desktop-1536x1024.png`,
  `task-5-compare-desktop-1536x1024.png`,
  `task-5-compare-mobile-390x844-exact.png`,
  `task-5-decision-mobile-390x844-exact.png`,
  `task-5-review-mobile-fixed.png`, `task-5-finalized-desktop.png`,
  `task-5-finalized-mobile.png`.

## Friss validáció

- `python -m unittest discover -s .\skills\peter-irta\tests -p 'test_*.py'`
  → 63/63 PASS.
- `python -m py_compile (Get-ChildItem .\skills\peter-irta\scripts\*.py)`
  → exit 0.
- `node --check .\skills\peter-irta\assets\human-blind-test\app.js`
  → exit 0.
- `quick_validate.py .\skills\peter-irta` → `Skill is valid!`, exit 0.
- `git diff --check` → exit 0; csak az ismert Windows LF→CRLF figyelmeztetés.
- A szerver listener ellenőrzése: kizárólag `127.0.0.1:8766`, külső bind nincs.

## Kötelező értelmezési korlátok

- A final result minden esetben:
  `utility_written=false`.
- A final result minden esetben:
  `learned_preference_claimed=false`.
- A final result minden esetben:
  `feedback_review_required=true`.
- Az emberi finalizálás evidencia, de nem ír automatikusan retrieval utilityt,
  nem állít tanult preference-et és nem tréningadat-elfogadás.
- Nem futott teljes RAG rebuild, release, deploy vagy MCP-adapter.
- A korábbi modellbenchmark Engine v3 14 – V1 10 – döntetlen 6 eredménye
  mérsékelt, pozícióérzékeny jelzés, nem robusztus fölény.
- A `3697` worktree sok, más feladathoz tartozó dirty változást tartalmaz;
  reset, széles stage vagy unrelated fájlmódosítás tilos.

## Következő emberi lépés

1. Péter nyissa meg a `http://127.0.0.1:8766/` címet és töltse ki a 30 vak párt.
2. A review képernyőn ellenőrizze a döntéseket, majd csak kész állapotban
   finalizáljon.
3. A létrejött `human-test-result.json` feedbackjeit külön emberi review kövesse.
4. Utility vagy preference csak külön, bizonyított review-döntés után írható.

## Folytatási prompt

> Folytasd a Mind Vault Engine v3 emberi vaktesztet a
> `docs/codex-handoff.md` alapján. A helyi szerver `127.0.0.1:8766` címen fut,
> a fő futás 0/30, nincs finalizálva. Ne írj utilityt és ne állíts tanult
> preference-et pusztán a finalizálásból; a feedback emberi review-t igényel.
> Őrizd meg a dirty worktree minden unrelated változását. Ne futtass teljes RAG
> rebuildet, release-t, deployt vagy MCP-adaptert külön kérés nélkül.
