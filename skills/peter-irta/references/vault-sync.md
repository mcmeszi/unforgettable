# „Szinkron” protokoll

## Trigger

Péter önálló `szinkron` üzenete, vagy kifejezett kérése a mind vault Drive-frissítésére.

## Folyamat

1. Olvasd be a `data/mind-vault/sync-state.json` állapotot és a két inventory TSV-t.
2. A kapcsolt Google Drive-ban járd be a gyökérdokumentumokat, az ismert irodalmi/slam-mappákat és a legutóbbi szinkron óta létrehozott vagy módosított szöveges fájlokat.
3. Azonosíts Drive ID alapján. Változásnál olvasd el a tartalmat, ne csak a címet.
4. Recall-first besorolás: saját irodalmi mű → `include-core`; saját tanulmány, prezentáció, beszéd, reklám vagy email → `include-secondary`; lehetséges saját anyag → `include-pending`; idegen szöveg → `reference-only`; admin, credential vagy zaj → `exclude`.
5. Normalizáld a címet és csatold a műcsaládhoz. Ne törölj régi változatot.
6. Frissítsd a `drive-root-documents.tsv`, `drive-content-classification.tsv`, az érdemi új találatokkal a forrásauditot, majd a `sync-state.json` állapotot.
7. Materializáld az új teljes szöveget a source-content rétegbe, majd építsd újra a summarykat és a RAG-ot a workspace meglévő scriptjeivel.
8. Futtass három skill-smoke-ot a `vault_query.py` segítségével: egy kreatív műfajt, egy szakmai műfajt és egy friss témát. Ellenőrizd, hogy teljes evidence érkezik, nincs metadata-only vagy insufficient-ASR hangminta, és működik a canonical deduplikáció.
9. Ellenőrizd a `/mind-vault/api.php` JSON-ját és a 3D oldal betöltését.
10. Jelentsd röviden az új, módosult, műcsaládba vont, teljes szövegű, pending és kizárt darabszámot.

## Biztonság

Ne törölj vagy módosíts Drive-fájlt. Ne olvass vagy másolj ki credential tartalmat. Névazonosságú külső forrást ne vonj be automatikusan.

Ne indíts lokális LLM-es transcript-korrektúrát. Új vagy megváltozott ASR-leiratnál őrizd meg a raw fájlt, és indíts külön Codex „Mind Vault transcript update patch” feladatot. A skill csak az elfogadott review-hash után használhatja a corrected réteget.
