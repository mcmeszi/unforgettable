# Codex handoff — Mind Vault emberi vakteszt

Frissítve: 2026-08-18

## Cél és aktuális mérföldkő

A 30 briefes V1 retrieval vs Engine v3 emberi vakteszt final review hibái
javítva vannak. A valós, gitignore-olt pack frissen, közvetlenül az official
`benchmark-results.json` `briefs` alakjából készült. A fő felhasználói futás
0/30, nincs finalizálva, progress/result fájlja nem létezik. A javított szerver
rejtett ablakban, kizárólag `127.0.0.1:8766` címen fut; PID: `9300`.

## Azonnali használat

Nyisd meg: `http://127.0.0.1:8766/`

Ha a szervert később újra kell indítani, előbb ellenőrizd a 8766-os listener
PID-jét és annak command line-ját. Csak akkor állítsd le, ha pontosan ez a
checkout, ez a `human_blind_test_server.py`, ez a pack és a `--port 8766`
szerepel benne. Egyidejűleg csak egy szerver írhatja a fő progress/result párt.

```powershell
Start-Process -FilePath 'C:\Users\Mészáros Péter\AppData\Local\Programs\Python\Python312\python.exe' -ArgumentList @('"C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\scripts\human_blind_test_server.py"','--public','"C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\public-test.json"','--private','"C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\private-human-key.json"','--manifest','"C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\human-test-manifest.json"','--progress','"C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\human-test-progress.json"','--result','"C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\human-test-result.json"','--host','127.0.0.1','--port','8766') -WorkingDirectory 'C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy' -WindowStyle Hidden -PassThru
```

## Valós pack, hashok és állapot

Pack:
`C:\Users\Mészáros Péter\.codex\worktrees\3697\kisagy\skills\peter-irta\state\human-blind-test-30\`

- Seed: `20260818`.
- `public-test.json` raw SHA-256:
  `BE5B3A1F326D7CC0934C6AAF8F2067E36EC6027C71679154FDF2C5F38C19183E`.
- `private-human-key.json` raw SHA-256:
  `85FEF55B83C4C61B09622E8194B76B78EDAC5EFA7B76314BB1EE4503CF41A0D6`.
- `human-test-manifest.json` raw SHA-256:
  `353E083EAD02F81C378B750823DE1A222079CD0094E225F471309EE8886A8044`.
- Manifest public canonical SHA-256:
  `657cd2d171335654ae27fada6e384df58546df3f35f1e2c2f239dc47b849eef6`.
- Manifest private canonical SHA-256:
  `ce4efa8b08762b458b130121898c1bd7ab4a7f721651d63b94f8b92e7f451ba1`.
- 30 egyedi brief; 10 műfaj, mindegyikben 3 brief; 15 Engine-bal és 15
  legacy-bal.
- Első/második fél Engine-bal aránya: 9/6. A régi 15 Engine, majd 15
  legacy oldalblokk megszűnt.
- A public packban nincs `legacy`, `engine_v3`, exact `A`/`B` vagy `source_id`
  szivárgás.
- Fő API state: `item_count=30`, `answered_count=0`, `finalized=false`.
- Fő progress:
  `...\human-blind-test-30\human-test-progress.json` — jelenleg nem létezik.
- Fő result:
  `...\human-blind-test-30\human-test-result.json` — jelenleg nem létezik.

## Tételsorrend és oldalsorrend

Briefek tesztsorrendben:

1. `vers-03`
2. `tanulmany-01`
3. `slam-03`
4. `reklam-01`
5. `email-03`
6. `proza-01`
7. `prezentacio-02`
8. `slam-02`
9. `dalszoveg-03`
10. `vers-02`
11. `slam-01`
12. `beszed-03`
13. `reklam-02`
14. `tanulmany-02`
15. `cikk-03`
16. `dalszoveg-01`
17. `prezentacio-01`
18. `cikk-01`
19. `proza-02`
20. `cikk-02`
21. `beszed-02`
22. `beszed-01`
23. `prezentacio-03`
24. `email-01`
25. `reklam-03`
26. `tanulmany-03`
27. `dalszoveg-02`
28. `vers-01`
29. `proza-03`
30. `email-02`

Bal oldali rendszer sorrendje (`E` = Engine v3, `L` = legacy):

`L,L,E,E,L,L,E,E,L,E,L,E,E,E,E,L,E,L,E,L,E,L,L,L,E,E,L,E,L,L`

## Mentés és szerverbiztonság

- A `Mentés és tovább` az összes mezőt `/api/answer` alatt, ideiglenes
  fájl + atomi csere módszerrel menti.
- Reload/Back után a kliens `/api/progress` alatt visszatölti a döntést,
  indokot, flag-eket, mindkét jelölt kiemelését/jegyzetét és az általános
  megjegyzést.
- Finalizálás csak 30 érvényes válasznál lehetséges; utána az eredmény
  immutable, minden answer write HTTP 409.
- A POST csak `application/json` mellett fut. A `Host` pontosan az aktív
  `127.0.0.1:<port>`, a jelen levő `Origin` ugyanennek a HTTP originje lehet.
  Origin nélküli helyi CLI-kérés pontos Hosttal megengedett. Támadó Origin,
  `text/plain`, hamis Host és DNS-rebinding Host elutasítódik.
- A final result `run_id` alakja `hbt-<24 hex>`, és nem fed fel nyers útvonalat.
- A final result mindig `utility_written=false`, `learned_preference_claimed=false`
  és `feedback_review_required=true`. Emberi finalizálásból nem lesz
  automatikusan utility, preference vagy tréningadat-elfogadás.

## Final review QA és validáció

- A friss pack külön disposable browser futásban 30/30-ig, review-ig,
  finalizálásig és revealig ment.
- Reload/Back visszaállította az első döntést, két flaget, a Bal/Jobb
  kiemelést és jegyzetet, valamint az általános megjegyzést.
- Disposable run ID: `hbt-8735f8aeb5b43f2d7f74024c`; result SHA-256:
  `85D9EF8C2CBD199A8D05425DEA723AE3F288044774D9A4BA9BB632D042A59A94`.
- A második JSON írás 409, a browser `text/plain` mutáció 415.
- 1536×1024 desktop és 390×844 mobil nézetben nincs vízszintes overflow.
- QA riport:
  `.superpowers\sdd\2026-08-18-human-blind-test\final-review-fix-report.md`.
- Képek: `output\playwright\hbt-final-fix-review-desktop.png`,
  `hbt-final-fix-review-mobile.png`, `hbt-final-fix-results-desktop.png`,
  `hbt-final-fix-results-mobile.png`.
- Teljes skill suite: 77/77 PASS.
- Minden skill Python script `py_compile`: exit 0.
- Frontend `node --check`: exit 0.
- `quick_validate.py`: `Skill is valid!`.
- `git diff --check`: exit 0; csak ismert Windows LF→CRLF warning.
- Listener: kizárólag `127.0.0.1:8766`, PID `9300`, root HTTP 200.

## Korlátok és következő lépések

- Nem futott teljes RAG rebuild, release, deploy vagy MCP-adapter.
- A korábbi modellbenchmark 14 Engine v3 – 10 V1 – 6 döntetlen eredménye
  mérsékelt, pozícióérzékeny jelzés, nem robusztus fölény.
- A `3697` worktree sok unrelated dirty változást tartalmaz; reset, széles
  stage vagy unrelated módosítás tilos.
- Péter következő lépése: megnyitni a `http://127.0.0.1:8766/` címet,
  kitölteni a 30 párt, review-zni, majd csak kész állapotban finalizálni.
- A létrejött `human-test-result.json` feedbackjeit külön emberi review
  kövesse; utility vagy preference csak bizonyított review-döntés után írható.

## Folytatási prompt

> Folytasd a Mind Vault Engine v3 emberi vaktesztet a `docs/codex-handoff.md`
> alapján. A javított helyi szerver `127.0.0.1:8766` címen fut, a fő futás
> 0/30, nincs finalizálva. Ne írj utilityt és ne állíts tanult preference-et
> pusztán a finalizálásból; a feedback emberi review-t igényel. Őrizd meg
> az unrelated dirty worktree-változásokat. Ne futtass teljes RAG rebuildet,
> release-t, deployt vagy MCP-adaptert külön kérés nélkül.
