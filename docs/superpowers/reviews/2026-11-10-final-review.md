# Final whole-branch review — d74598c..4b106b9 (24 commits)

Reviewer: deepseek-v4.1-flash-free (ses_e39711347ffe; hit step limit before writing this file — content condensed from the returned report; full verdict details preserved below and in the ledger).
Method: four passes (plan/spec/ledger + commit inventory; engine + pdf reconstruction; fs/write + state + main + render with end-to-end Rename gesture trace; PWA shell/dist/README + constraint verification + deferred-minor triage). Suites not re-run — ledger gate results used (191/191 vitest, 62/62 parity, 177 pytest, build 0).

## Verdict: Ready to merge? **With fixes**

## Strengths (condensed)
- Clean testable layering: planRenames pure, state pure except bounded pool, write.ts owns all IO, render.ts dumb with zero innerHTML.
- Write semantics honored as a whole: single write under final name (write.ts:127), write-time probe (write.ts:175-190), manual-only sanitize, triple-guarded excluded rows (state.ts:124-128, main.ts:427, write.ts:119-121), move-after-write (write.ts:127-135), non-recursive scan (scan.ts:11-24).
- Gesture contract careful: query-only restore (main.ts:151-175), permission requests synchronous before first await (main.ts:240-252).
- Security: all user strings via textContent; no HTML sinks; no runtime network; expected.json untracked+gitignored; *.pdf ignored.
- PWA correct at HEAD: real PNG icons, both worker chunks + 14 fonts + icons + manifest precached (25 entries), manifest types/scope correct, port 4173 pinned.
- Python package untouched (empty diff on pdf_sort/ tests/); parity + pytest recorded at HEAD.
- Engine/test quality: real transcriptions, no .skip/.only/.todo; write-collision test honest; in-flight counter test real.
- UI hardening from fix rounds present (focus restoration, deferred render, idempotent commit, retry-once collision).

## Issues

### Critical (Must Fix)
1. **Worker seam** — `app/src/pdf/text.ts:16-29` + `:119-154` with `app/src/state.ts:22,74-78`:
   - Latch-before-await: `workerPortReady = true` set BEFORE `await import(...)`; parseAll's 4 concurrent workers → up to 3 calls `getDocument` with `GlobalWorkerOptions.workerPort` unset and `workerSrc` unset → pdf.js falls to fake-worker setup which throws `No "GlobalWorkerOptions.workerSrc" specified.` → good receipts render as ✕.
   - Shared port + per-document `loadingTask.destroy()` = documented-unsafe pdf.js combination (mozilla/pdf.js#16777): first destroy tears down the shared worker while siblings parse → intermittent error rows or a scan that never resolves.
   - Fix: cache the init promise (`??=` after await); eliminate shared-destroy (per-document worker via `workerSrc` set from a browser-only dynamic `?url` import — verify dist still emits the worker chunk — or one explicitly-owned PDFWorker never destroyed per-document); add a concurrency test; ideally a real Chrome 4-receipt cold-load smoke test.

### Important (Should Fix)
2. **Unguarded processed/ copy** — `app/src/fs/write.ts:129-135`: `writeBytes(processedDir, row.original, ...)` uses `{create:true}` with no probe → a repeat download name (comprobante.pdf) silently destroys the previously archived original while reporting `moved`. Fix: probe `processed/` BEFORE the output write; exists → loud row failure, original untouched, batch continues; add the test.
3. **storage.persist() never called** — spec:73 requires `navigator.storage.persist()` (folder memory durability); absent from `app/src/fs/handles.ts`. Fix: call once from a user gesture (first Choose/Scan, latched), guard for non-Chromium, note in README. (Plan omitted this step — plan/spec gap, flagged to executor.)

### Minor (Nice to Have) — numbered findings #4-#15
4. `handles.ts:3-5` pickFolder without `{mode:'readwrite'}` → immediate post-pick permission reads may say "prompt", double-prompting.
5. `state.ts:126-128`/`write.ts:125-127` manual name without `.pdf` written with no extension (placeholder promises `filename.pdf`; nothing enforces).
6. `main.ts:374-380` + `render.ts:82-97` rows not retired after a successful run → second Rename click creates duplicate `_2` outputs (and reports failures with moveProcessed). **FIXED** — terminal `"done"` status added to `RowStatus`; `computePlan()` skips done rows; retirement logic in `rename()`.
7. `render.ts:124-138` empty-state instruction renders simultaneously with the progress bar during scan.
8. `main.ts:358-373` duplicate/overwritten collision notices (Cancel message overwritten by remainingCollisions notice).
9. `render.ts:238-256` incomplete rows never show planned final name (incl. `_2` dedup suffixes) — visual dry-run promise incomplete. **FIXED** — `renderRows()` now shows finalName when committed; input shown only while `finalName === null`.
10. `main.ts:436` write bytes from scan-time File snapshot while `removeEntry` deletes current path (replace-between-scan-and-rename). **FIXED** — `ScanEntry` now carries a `handle`; `toRenameRows()` fetches fresh bytes at write time via `handle.getFile()`.
11. `state.ts:146` parse-error rows counted "skipped" in summary. PARKED.
12. `render.ts:199` arrow `<th>` empty label (screen readers).
13. `main.ts:32-38` mouseDown latch stuck if released outside window (view-only). **FIXED** — added `document.mouseup` + `window.blur` listeners; `setMouseDown()` helper centralizes the latch.
14. `main.ts:340-362` write-time collision retry all-or-nothing, not per-row (rare). PARKED.
15. `handles.ts:18-25` saveHandle resolves on put success, not tx.oncomplete (durability nit). PARKED.
16. Test gap: main.ts orchestration + browser worker path untested (text.test.ts mocks pdf.js; MODE short-circuits ensureWorkerPort) — the code that fails in #1 has no coverage. PARKED as follow-up (browser smoke test recommended).

## Deferred-Minor Triage (48 ledger items)
2 MUST-FIX (worker race, processed copy — now findings #1/#2), 46 LEAVE (full item-by-item list in ledger + review reply: Tasks 1-13 deferrals — pdfjs in devDeps, smoke test, npm vulns, TS 7.0.2 pin, prototype-chain lookups, Unicode titlecase, regex dialect edges, date-assert strength, Python crash divergences, dead guards, fmtAmount finite guard, report miscounts, dedup corner, ASCENT retune trigger, fake fidelity nits, db.close, suffix-alias parity, output/processed split untested, auto-sanitize pin, e2e checklist nits, scan() failure state, mouseDown latch, double render, dead flush, Tab focus).

## Declined to judge (executor rules on each)
Two tabs concurrent; input==output folder; non-Latin/CMap PDFs; Windows reserved names; physical move semantics; post-success state reset; maskable icons; SW update/reload UX; ported-fixture provenance.

## Recommendations
1. Fix worker seam first + cold-start 4-receipt browser e2e.
2. Guard processed/ copy with loud probe before output write.
3. Add storage.persist() + note plan/spec delta.
4. One jsdom integration test for main.ts orchestration (Scan → manual name → Rename → collision retry).
5. .pdf rule for manual names + retire rows post-run.
6. Keep deferred test-strength items on a follow-up list.
