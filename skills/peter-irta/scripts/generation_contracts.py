#!/usr/bin/env python3
"""Genre-specific generation and release contracts for peter-irta outputs."""

from __future__ import annotations

from copy import deepcopy


GENRE_ALIASES = {
    "beszéd": "beszed",
    "dalszöveg": "dalszoveg",
    "prezi": "prezentacio",
    "prezentáció": "prezentacio",
    "próza": "proza",
    "reklám": "reklam",
    "tanulmány": "tanulmany",
}

COMMON_RELEASE_CHECKS = [
    {
        "id": "cliche-specificity",
        "question": "A kész fordulatok helyett van-e konkrét, briefből származó helyzet, tárgy vagy megfigyelés?",
    },
    {
        "id": "syntax-semantic-coherence",
        "question": "Minden mondat nyelvtanilag természetes, és a hasonlat gondolati logikája első olvasásra követhető?",
    },
    {
        "id": "motif-budget",
        "question": "A technológia és más visszatérő Péter-motívum csak a brief által indokolt mértékben szerepel?",
    },
]

GENRE_CONTRACTS = {
    "beszed": {
        "composition_recipe": ["konkrét közönséghelyzet", "szerves gondolati váltás", "élő ritmus", "nem közhelyes visszakötés"],
        "release_checks": [{"id": "live-specificity", "question": "A beszéd helyben és emberekhez szól, nem általános ünnepi sablon?"}],
        "hard_fail_if": ["felolvasva merev", "a fő érzelmi állítás közhelyekből áll"],
    },
    "cikk": {
        "composition_recipe": ["pontos tézis", "érthető példa", "puhító váltás", "ellenpont", "gyakorlati következmény"],
        "release_checks": [{"id": "tonal-balance", "question": "A humor puhítja, de nem töri meg a szakmai állítást és az érvelési ritmust?"}],
        "hard_fail_if": ["természetellenes mondatlogika", "a hasonlat nem ugyanazt az állítást bizonyítja"],
    },
    "dalszoveg": {
        "composition_recipe": ["énekelhető érzelmi mag", "új információt adó verzék", "hangzásból is működő refrén", "nem kézenfekvő rímkapcsolatok"],
        "release_checks": [{"id": "rhyme-prosody", "question": "A rím természetes hangsúlyú, változatos, énekelhető és jelentést is sűrít?"}],
        "hard_fail_if": ["a rím csak toldalék- vagy végződésegyezés", "a sor természetes hangsúlya megtörik", "a refrén közhelyet ismétel"],
    },
    "email": {
        "composition_recipe": ["miért írok", "szükséges információ", "egyértelmű kérés", "kapcsolathoz illő lezárás"],
        "release_checks": [{"id": "relationship-distance", "question": "A közvetlenség illik a címzetti viszonyhoz, indokolatlan önhibáztatás és bizalmaskodás nélkül?"}],
        "hard_fail_if": ["a kérés vagy következő lépés nem egyértelmű", "a hangnem közelebbinek tetteti a kapcsolatot a briefnél"],
    },
    "prezentacio": {
        "composition_recipe": ["diánként egy narratív funkció", "előző diából következő átmenet", "változó, indokolt body-sűrűség", "cselekvésbe futó zárlat"],
        "release_checks": [{"id": "slide-flow", "question": "A diacímek önmagukban logikai történetet adnak, és minden dia előkészíti a következőt?"}],
        "hard_fail_if": ["a diák felcserélhetők jelentésvesztés nélkül", "a tömörség miatt hiányzik a logikai átmenet"],
    },
    "proza": {
        "composition_recipe": ["működés közbeni jelenet", "egy világalkotó abszurd szabály", "fanyar humor", "döntés és következmény"],
        "release_checks": [{"id": "image-system", "question": "Minden fontos kép ugyanazt a világ- vagy motívumtörvényt mélyíti?"}],
        "hard_fail_if": ["a képek külön hatásokként versengenek", "a humor megszakítja a jelenetet vagy semlegesíti a tétet"],
    },
    "reklam": {
        "composition_recipe": ["konkrét megfigyelt viselkedés", "emberi feszültség", "márkaspecifikus bizonyíték", "kreatív állítás", "CTA"],
        "release_checks": [{"id": "behavioral-insight", "question": "Az insight konkrét emberi mikroszituációból indul, nem egy evidens kategóriaanalógiából?"}],
        "hard_fail_if": ["az insight bármely konkurenssel működne", "a szóvicc előbb érkezik, mint a megfigyelés"],
    },
    "slam": {
        "composition_recipe": ["azonnal hallható premissza", "kimondható fokozás", "közönségkapcsolat", "személyes lejtő", "callback"],
        "release_checks": [{"id": "spoken-orality", "question": "Egyszeri hallásra követhető és levegővel kimondható, nem sortördelt lapvers?"}],
        "hard_fail_if": ["a jelentés csak visszaolvasva áll össze", "a technológiai motívumok katalógussá válnak"],
    },
    "tanulmany": {
        "composition_recipe": ["gondolatébresztő problémafelvetés", "definíció", "érvelő próza", "méltányos ellenpont", "kutatható következő lépés"],
        "release_checks": [{"id": "prose-surface", "question": "A hipotézis- és bizonyítéktérkép belső szerkezet marad, miközben a kész szöveg olvasmányos próza?"}],
        "hard_fail_if": ["a belső váz minden bekezdésen látható címkévé válik", "a forráshiányt száraz ismétlések helyettesítik"],
    },
    "vers": {
        "composition_recipe": ["egy konkrét kép", "egy képi törvény", "szűkülő jelentés", "lebegtető visszakötés"],
        "release_checks": [{"id": "image-system", "question": "A képek egyetlen érthető rendszert építenek, képzavar és túlfeszítés nélkül?"}],
        "hard_fail_if": ["egy kép nem értelmezhető a vers saját világán belül", "a zárlat elmagyarázza a jelentést"],
    },
}


def normalize_genre(genre: str) -> str:
    value = str(genre or "").strip().lower()
    return GENRE_ALIASES.get(value, value)


def genre_quality_contract(genre: str) -> dict:
    normalized = normalize_genre(genre)
    if normalized not in GENRE_CONTRACTS:
        raise ValueError(f"Unsupported peter-irta genre: {genre}")
    contract = deepcopy(GENRE_CONTRACTS[normalized])
    contract["genre"] = normalized
    contract["release_checks"] = [*deepcopy(COMMON_RELEASE_CHECKS), *contract["release_checks"]]
    return contract
