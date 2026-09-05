# Mind Vault Human Blind Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, single-evaluator browser test that compares all 30 blinded V1 and Engine v3 draft pairs and reveals systems only after every verdict is finalized.

**Architecture:** A deterministic Python preparer creates a public pack, a private position key, and a hash manifest. A loopback-only standard-library HTTP server owns progress, validation, finalization, and unblinding; a dependency-free HTML/CSS/JavaScript client displays one comparison at a time. Runtime inputs and human results stay under the ignored skill `state/` directory.

**Tech Stack:** Python 3.12 standard library, `unittest`, semantic HTML, vanilla CSS and JavaScript, local JSON files, Browser/IAB visual QA.

## Global Constraints

- Use all 30 unique benchmark briefs with exactly 3 briefs from each of 10 genres.
- Select briefs and positions deterministically from an explicit seed.
- Place Engine v3 on the left exactly 15 times and on the right exactly 15 times.
- Never expose `legacy`, `engine_v3`, `A`, `B`, source IDs, or provenance mappings in the public pack.
- Bind only to `127.0.0.1`; make no external network requests and add no runtime dependency.
- Require `left`, `right`, or `tie` plus a reason of at least 10 trimmed characters.
- Allow per-candidate optional highlighted excerpts up to 500 characters, per-candidate notes up to 1500 characters, and one general note up to 1500 characters.
- Reject finalization until all 30 answers are valid; finalized runs are immutable.
- Never write retrieval utility, voice feedback, or learned reranker preference.
- Keep packs, private keys, progress, and results under gitignored `skills/peter-irta/state/`.
- Do not rebuild RAG, release, deploy, or add an MCP adapter.

---

### Task 1: Deterministic public pack and private key

**Files:**
- Create: `skills/peter-irta/scripts/human_blind_test.py`
- Create: `skills/peter-irta/scripts/prepare_human_blind_test.py`
- Create: `skills/peter-irta/tests/test_human_blind_test.py`

**Interfaces:**
- Consumes: benchmark result dict, generation-job records, draft directory, blind-key dict, integer seed.
- Produces: `benchmark_briefs(result: dict) -> list[str]`, `build_pack(...) -> tuple[dict, dict, dict]`, `validate_public_pack(pack: dict) -> list[str]`, and three JSON files from the CLI.

- [ ] **Step 1: Write failing selection and blinding tests**

```python
def test_selection_keeps_all_thirty_briefs_and_three_per_genre(self):
    selected = human_blind.benchmark_briefs(self.benchmark_result())
    self.assertEqual(len(selected), 30)
    self.assertEqual(len(set(selected)), 30)
    counts = Counter(self.genre_by_brief[item] for item in selected)
    self.assertEqual(set(counts), set(self.genres))
    self.assertTrue(all(count == 3 for count in counts.values()))

def test_public_pack_is_balanced_and_contains_no_system_mapping(self):
    public, private, manifest = human_blind.build_pack(
        self.result, self.jobs, self.drafts, self.blind_key, seed=20260818
    )
    self.assertEqual(len(public["items"]), 30)
    self.assertEqual(sum(value["left"] == "engine_v3" for value in private["items"].values()), 15)
    serialized = json.dumps(public, ensure_ascii=False)
    for forbidden in ("legacy", "engine_v3", '"A"', '"B"', "source_id"):
        self.assertNotIn(forbidden, serialized)
    self.assertEqual(manifest["public_sha256"], human_blind.canonical_sha256(public))
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python -m unittest discover -s .\skills\peter-irta\tests -p 'test_human_blind_test.py' -v`

Expected: import failure because `human_blind_test.py` does not exist.

- [ ] **Step 3: Implement the minimal pack builder**

Implement these exact functions in `human_blind_test.py`:

```python
def canonical_sha256(payload: dict) -> str: ...
def benchmark_briefs(result: dict) -> list[str]: ...
def balanced_positions(brief_ids: list[str], seed: int) -> dict[str, bool]: ...
def build_pack(result: dict, jobs: list[dict], drafts_dir: Path,
               blind_key: dict, seed: int) -> tuple[dict, dict, dict]: ...
def validate_public_pack(pack: dict) -> list[str]: ...
```

Validate that the benchmark contains 30 unique briefs and exactly three per genre, then retain all of them. Shuffle presentation with `random.Random(seed)`. Select 15 shuffled IDs for Engine-left and invert candidate text positions through the private blind key. Public items contain opaque `item_id`, `brief_id`, `genre`, `brief`, `left_text`, `right_text`, and draft hashes only.

- [ ] **Step 4: Implement the preparer CLI**

The CLI requires `--results`, `--jobs`, `--drafts-dir`, `--blind-key`, `--seed`, and `--output-dir`; refuse a non-empty output directory. Write `public-test.json`, `private-human-key.json`, and `human-test-manifest.json` with UTF-8 and deterministic JSON formatting.

- [ ] **Step 5: Run focused and full tests**

Run:

```powershell
python -m unittest discover -s .\skills\peter-irta\tests -p 'test_human_blind_test.py' -v
python -m unittest discover -s .\skills\peter-irta\tests -p 'test_*.py'
```

Expected: focused tests PASS; full suite reports 0 failures.

- [ ] **Step 6: Commit Task 1**

```powershell
git add skills/peter-irta/scripts/human_blind_test.py skills/peter-irta/scripts/prepare_human_blind_test.py skills/peter-irta/tests/test_human_blind_test.py
git commit -m "Build deterministic human blind pack"
```

---

### Task 2: Loopback server, progress, and finalization

**Files:**
- Create: `skills/peter-irta/scripts/human_blind_test_server.py`
- Modify: `skills/peter-irta/scripts/human_blind_test.py`
- Modify: `skills/peter-irta/tests/test_human_blind_test.py`

**Interfaces:**
- Consumes: public pack, private key, manifest, progress path, result path.
- Produces: `BlindTestRun` methods `save_answer`, `snapshot`, and `finalize`; HTTP endpoints `/api/test`, `/api/progress`, `/api/answer`, `/api/finalize`, `/api/results`.

- [ ] **Step 1: Write failing state-contract tests**

```python
def test_answer_requires_known_item_choice_and_reason(self):
    run = self.make_run()
    with self.assertRaisesRegex(ValueError, "reason"):
        run.save_answer("item-01", "left", "rövid")
    with self.assertRaisesRegex(ValueError, "choice"):
        run.save_answer("item-01", "engine_v3", "legalább tíz karakter")

def test_candidate_notes_are_bounded_and_unblinded_to_the_correct_system(self):
    run = self.make_run()
    with self.assertRaisesRegex(ValueError, "500"):
        run.save_answer("item-01", "left", "legalább tíz karakter",
                        left_highlight="x" * 501)
    run.save_answer("item-01", "left", "legalább tíz karakter",
                    left_highlight="ez a sor tetszett",
                    left_note="feszes és természetes",
                    right_note="jó kép, de modoros")
    self.answer_remaining(run)
    item = run.finalize()["items"][0]
    self.assertEqual(item["candidate_feedback"]["engine_v3"]["highlight"],
                     "ez a sor tetszett")

def test_finalize_is_blocked_until_complete_then_becomes_immutable(self):
    run = self.make_run()
    with self.assertRaisesRegex(RuntimeError, "30"):
        run.finalize()
    self.answer_all(run)
    result = run.finalize()
    self.assertEqual(sum(result["overall"].values()), 30)
    self.assertFalse(result["utility_written"])
    self.assertFalse(result["learned_preference_claimed"])
    with self.assertRaisesRegex(RuntimeError, "finalized"):
        run.save_answer("item-01", "right", "utólag már nem írható át")
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m unittest discover -s .\skills\peter-irta\tests -p 'test_human_blind_test.py' -v`

Expected: failures because `BlindTestRun` is undefined.

- [ ] **Step 3: Implement `BlindTestRun`**

Use this constructor and methods:

```python
class BlindTestRun:
    def __init__(self, public: dict, private: dict, manifest: dict,
                 progress_path: Path, result_path: Path): ...
    def snapshot(self) -> dict: ...
    def save_answer(self, item_id: str, choice: str, reason: str,
                    flags: list[str] | None = None,
                    left_highlight: str = "", right_highlight: str = "",
                    left_note: str = "", right_note: str = "",
                    general_note: str = "") -> dict: ...
    def finalize(self) -> dict: ...
```

Validate manifest hashes on construction. Store only item ID, choice, trimmed reason, allowed flags, bounded optional candidate highlights/notes, general note, and timestamps in progress. Write through a sibling temporary file and `Path.replace`. On finalize, translate the chosen position and both candidate-feedback blocks through the private key, aggregate overall and by genre, include draft hashes but no full text, set both learning flags to `false`, and set `feedback_review_required` to `true`.

- [ ] **Step 4: Implement the HTTP adapter**

Use `ThreadingHTTPServer` and a request handler factory receiving a `BlindTestRun`. Parse and emit UTF-8 JSON. Map validation errors to 400, incomplete/finalized conflicts to 409, and unknown routes to 404. Reject any `--host` other than `127.0.0.1`; default to an available port or explicit `--port`.

- [ ] **Step 5: Run focused and full tests**

Run the focused file and full  `test_*.py` discovery. Expected: all PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add skills/peter-irta/scripts/human_blind_test.py skills/peter-irta/scripts/human_blind_test_server.py skills/peter-irta/tests/test_human_blind_test.py
git commit -m "Serve immutable local blind test"
```

---

### Task 3: Browser interface

**Files:**
- Create: `skills/peter-irta/assets/human-blind-test/index.html`
- Create: `skills/peter-irta/assets/human-blind-test/app.css`
- Create: `skills/peter-irta/assets/human-blind-test/app.js`
- Modify: `skills/peter-irta/scripts/human_blind_test_server.py`
- Modify: `skills/peter-irta/tests/test_human_blind_test.py`

**Interfaces:**
- Consumes: the Task 2 JSON API.
- Produces: start, comparison, review, finalized reveal, loading, and error UI states.

- [ ] **Step 1: Generate the complete visual concept and obtain approval**

Use Image Gen for one complete desktop comparison screen and one mobile state. Specify editorial reading focus, neutral system labels, equal visual weight, no badges/gradients/card-grid treatment, and code-native Hungarian controls. Do not implement until Péter approves the concept.

- [ ] **Step 2: Write failing static-contract tests**

```python
def test_frontend_assets_and_required_copy_exist(self):
    asset_root = Path(__file__).resolve().parents[1] / "assets" / "human-blind-test"
    html = (asset_root / "index.html").read_text(encoding="utf-8")
    script = (asset_root / "app.js").read_text(encoding="utf-8")
    self.assertIn('id="left-candidate"', html)
    self.assertIn('id="right-candidate"', html)
    self.assertIn('id="left-highlight"', html)
    self.assertIn('id="left-note"', html)
    self.assertIn('id="right-highlight"', html)
    self.assertIn('id="right-note"', html)
    self.assertIn("Véglegesítés", html)
    self.assertIn("/api/answer", script)
    self.assertIn("/api/finalize", script)
```

- [ ] **Step 3: Run the static-contract test and verify RED**

Expected: missing `assets/human-blind-test/index.html`.

- [ ] **Step 4: Implement the approved design system and HTML**

Extract exact colors, typography, spacing, borders, radii, and responsive rules from the approved concept. Use semantic landmarks, two equal reading columns at desktop, stacked candidates below 760 px, visible keyboard focus, and `prefers-reduced-motion`. All UI text and controls remain native HTML.

- [ ] **Step 5: Implement the interaction state machine**

`app.js` owns `start`, `compare`, `review`, and `finalized` states. Each candidate column includes optional highlighted-excerpt and positive-note fields; the pair includes an optional general note. Disable Next until choice and 10-character reason are present. Save all fields through `/api/answer`, reload through `/api/progress`, show no score during the run, confirm before `/api/finalize`, and render the returned unblinded overall, per-item result, and system-bound candidate feedback.

- [ ] **Step 6: Run static-contract and full tests**

Expected: all PASS and no browser console syntax errors.

- [ ] **Step 7: Commit Task 3**

```powershell
git add skills/peter-irta/assets/human-blind-test skills/peter-irta/scripts/human_blind_test_server.py skills/peter-irta/tests/test_human_blind_test.py
git commit -m "Add local human blind test interface"
```

---

### Task 4: Produce the real 30-pair human benchmark

**Files:**
- Modify: `skills/peter-irta/references/engine-v3.md`
- Generate, do not commit: `skills/peter-irta/state/human-blind-test-30/`

**Interfaces:**
- Consumes: the completed 30-brief benchmark stored in the local runtime skill state.
- Produces: one verified local 30-pair benchmark pack and exact launch command.

- [ ] **Step 1: Run the preparer with the fixed benchmark seed**

Use seed `20260818` and the completed benchmark inputs. Write to `skills/peter-irta/state/human-blind-test-30/`. If the repository copy does not contain the private state, pass explicit absolute input paths from the local runtime skill; do not copy source state into Git.

- [ ] **Step 2: Verify benchmark invariants**

Run a Python assertion command proving 30 unique briefs, exactly three per genre, 15/15 Engine position balance, valid manifest hashes, and zero forbidden public tokens. Record the selected brief IDs in the handoff, not in committed private key material.

- [ ] **Step 3: Document preparation and launch commands**

Add portable PowerShell examples to `references/engine-v3.md` using explicit input flags and `MIND_VAULT_RAG_ROOT` where relevant. State that finalization creates human evidence but no utility entry.

- [ ] **Step 4: Commit Task 4 documentation only**

```powershell
git add skills/peter-irta/references/engine-v3.md
git commit -m "Document human blind benchmark workflow"
```

---

### Task 5: Browser QA, verification, and handoff

**Files:**
- Modify: `docs/codex-handoff.md`
- Modify as fixes require: Task 1–3 source and tests.

**Interfaces:**
- Consumes: the real 30-pair benchmark and complete local app.
- Produces: verified runnable browser test, screenshots, updated handoff, and updated draft PR.

- [ ] **Step 1: Start the local server**

Launch with the real benchmark paths and an unused loopback port. Confirm the reported URL is `http://127.0.0.1:<port>/` and no external bind exists.

- [ ] **Step 2: Verify the core workflow in Browser/IAB**

Open the local URL. Check start → first answer with candidate highlights/notes → refresh/reload persistence → back navigation → remaining answers → review. In a disposable copied progress file, complete all 30 and verify finalization, reveal, and correct system binding of both candidates' feedback. Confirm a second write is rejected.

- [ ] **Step 3: Perform visual QA against the approved concept**

Capture desktop at the concept's native size and mobile near 390×844. Use `view_image` on the approved concepts and latest screenshots. Compare at least copy, column equality, typography, palette, spacing, control states, long-text scrolling, and mobile order. Fix every material mismatch and repeat screenshots.

- [ ] **Step 4: Run final automated validation**

```powershell
python -m unittest discover -s .\skills\peter-irta\tests -p 'test_*.py'
python -m py_compile (Get-ChildItem .\skills\peter-irta\scripts\*.py)
python -X utf8 C:\Users\Mészáros` Péter\.codex\skills\.system\skill-creator\scripts\quick_validate.py .\skills\peter-irta
git diff --check
```

Expected: all tests PASS, compile exit 0, skill valid, and no whitespace errors.

- [ ] **Step 5: Update the handoff**

Record the launch command, selected brief IDs, validation evidence, local artifact paths, remaining human action, and the constraints that utility and learned preference remain false. Preserve every unrelated dirty worktree change.

- [ ] **Step 6: Commit and push the completed unit**

Stage only `skills/peter-irta/` implementation/docs and `docs/codex-handoff.md`; inspect `git diff --cached --name-only` before committing. Push `codex/version-peter-irta-engine-v3` and update draft PR #1. Do not merge or mark ready for review without Péter's request.
