# Final Project Audit — Sovereign On-Premise Agentic AI Workbench

**Audit date:** 2026-10-25<br>
**Audited revision:** `main`, `07b5089` (working tree contains uncommitted project changes)<br>
**Disposition:** Controlled academic demonstration: **GO, with the limits below**. Real industrial deployment: **NO-GO**.

This audit is based on the saved live logs and JSON reports, the current working tree, and fresh verification commands. It does not certify the system, prove complete air-gap isolation, or establish universal reliability.

## Verification summary

| Check | Actual result | Evidence / limits |
|---|---|---|
| Current full pytest suite | **276 collected; 275 passed, 0 failed, 1 skipped** in 56.95 s | `python -m pytest -o 'addopts=--tb=short' -q -ra --basetemp=eval\\.pytest-audit-full-confirm`; final skip is Windows symlink creation restriction. Includes 22 tests under `tests/test_integration/`; the remaining 254 are unit/component/security tests. |
| Focused OCR/evaluation tests | **44 passed** | OCR, quantitative metrics, dataset integrity, and runner/CLI test modules; workspace-local basetemp. |
| Model-backed full-suite first attempt | **274 passed, 1 failed, 1 skipped** | One live model refusal assertion did not contain its expected refusal wording. The exact isolated test passed on immediate rerun; the subsequent full confirmation passed. This exposes response variability in that assertion. |
| Full suite with Ollama unavailable | **259 passed, 2 failed, 15 skipped** | Two tests attempted local model inference despite unavailable Ollama; 15 explicitly skipped model tests. This is an environment-unavailable run, not the final acceptance count. |
| Frontend production build | **Passed** | `npm run build`; TypeScript build plus Vite, 1,938 modules, output built successfully. |
| Frontend lint | **Passed** | `npm run lint` (oxlint). |
| Ruff | **Passed** | `.venv\\Scripts\\ruff.exe check .` — all checks passed. |
| Mypy | **Passed** | `.venv\\Scripts\\mypy.exe app` — no issues in 73 source files. |
| Air-gap verifier | **6/6 checks passed** | `.venv\\Scripts\\python.exe scripts\\verify_airgap.py`; verifier itself states OS firewall rules are required for full isolation. |
| Live acceptance workflow | **Passed in the separately saved final run** | Analyst/admin login, synthetic document upload/indexing, semantic retrieval, locally generated response with validated citation, DOCX/XLSX creation/download, admin authorization, and traversal blocking; details below. |
| Docker sandbox tests | **Not verified** | Docker Desktop engine named pipe/daemon unavailable. The compose profile was checked by the verifier, but containers were not launched. |
| Full browser UI workflow | **Not verified** | Browser page and sign-in UI rendered; no browser login or workflow was submitted in that UI session. API-level live acceptance is covered by its separate log. |

### Test collection and categories

The current collection has **276 tests**: 22 integration tests under `tests/test_integration/` and 254 unit/component/security tests elsewhere. In the final model-enabled run, 275 passed and the only skip was `tests/test_tools/test_adversarial_security.py:71`, because this Windows environment does not permit symlink creation. All integration tests passed in that final run. A previous full run without Ollama had two model-connection failures and 15 optional skips; a separate model-enabled run had one nondeterministic refusal-phrase assertion fail, which passed in isolation and in the final full rerun.

Commands used for the final verification:

```powershell
$env:OLLAMA_NO_CLOUD='1'
.venv\Scripts\python.exe -m pytest -o 'addopts=--tb=short' -q -ra --basetemp=eval\.pytest-audit-full-confirm
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe app
.venv\Scripts\python.exe scripts\verify_airgap.py
npm run build       # from frontend/
npm run lint        # from frontend/
```

The separate focused run was:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_knowledge\test_ocr.py tests\test_eval\test_quantitative_metrics.py tests\test_eval\test_dataset_integrity.py tests\test_eval\test_runner_and_cli.py -q -ra --basetemp=eval\.pytest-audit-temp
```

An initial focused invocation without a workspace-local `--basetemp` could not create pytest's default temp directory under the restricted Windows sandbox; rerunning with the workspace-local temp directory passed. This was a test-environment setup issue, not a test assertion failure.

## Live end-to-end acceptance evidence

The latest durable browser-driven result is `eval/post-audit-2026-10-26-completion/browser_acceptance_verified-final-explicit-docx-2026-10-26.json`. It records **13/13** checks for synthetic login, upload, Knowledge Hub chunk inspection, RAG retrieval, grounded citation inspection/navigation, DOCX/XLSX generation and downloads, and browser errors. The API responses in that run were captured by the Chrome/Playwright harness; this is distinct from API-only tests.

An earlier version of this audit referenced `eval/live_e2e_acceptance_final.log` and `eval/live_e2e_acceptance.log` for a concise successful API acceptance and a separate failed citation attempt. Neither raw `.log` file is present in the current checkout, so those historical claims cannot be reopened from this repository snapshot. The current browser JSON record is present and is the primary end-to-end evidence included with this update. Do not treat the absent historical log filenames as files committed by this audit.

## OCR quality and measured change

### Saved live evaluation reports

[live_e2e_quantitative.md](live_e2e_quantitative.md) and its JSON record the earlier live evaluation with **4 OCR fixtures, 7.91% macro CER, 4.42% micro CER**, using `qwen3.5:4b`. In that report the ambiguous serial-tag fixture had **24.44% CER**. This is the baseline result requested for the audit.

The current production-style OCR run is saved in [final_live_ocr.md](final_live_ocr.md) and [final_live_ocr.json]. It evaluated the same four controlled fixtures with `qwen3.5:4b`: **4/4 available, 4.71% macro CER, 3.32% micro CER, mean WER 0.3167, mean keyword recall 0.7188**. Its ambiguous-tag CER was **13.33%**, still with WER 1.0 and zero expected-keyword recall. This is a measured single rerun; scores and latency are not a guarantee of future model output.

The experiment output [ocr_preprocessing_small_images.json](ocr_preprocessing_small_images.json) preserves full references and predictions for the paired comparison. It uses the same four fixture images and ground truth, model `qwen3.5:4b`, temperature 0, `num_predict=1024`, and `think=false`; the latter was held common to isolate the prompt/preprocessing change. The historical baseline call did not send `think=false`; an exact legacy attempt timed out before returning a scored prediction, so the paired baseline is not an exact replay of that historical request. No reference or ground-truth text was changed.

| Fixture | Ground-truth reference | Final small-image-preprocessing prediction | Edits (sub / del / ins; total) | CER | WER | Latency |
|---|---|---|---:|---:|---:|---:|
| Clean plate | `TURBINE GENERATOR TG-8500`<br>`SERIAL: SN-TG8500-2026-X`<br>`RATED CAPACITY: 1250 KW`<br>`OPERATING SPEED: 3600 RPM`<br>`MAX OIL TEMP: 85 C` | `TURBINE GENERATOR TG-8500`<br>`SERIAL: SN-TG8500-2026-X`<br>`RATED CAPACITY: 1250 KW`<br>`OPERATING SPEED: 3600 RPM`<br>`MAXOIL TEMP. 85 C` | 1 / 1 / 0; **2** | 1.68% | 0.1667 | 2,075.61 ms |
| Ambiguous serial tag | `TAG-0O1Il8B5S2Z`<br>`VALVE-O01-B8-S5-Z2`<br>`SER-1I0O8B` | `TAG-001IIB5S2Z`<br>`VALVE-C01-B8-S5-Z2`<br>`SER-110C8B` | 5 / 1 / 0; **6** | **13.33%** | **1.0000** | 1,699.13 ms |
| Pump telemetry table | `PUMP_ID PRESSURE_PSI FLOW_GPM TEMP_C STATUS`<br>`P-101 145.2 320 62.4 NOMINAL`<br>`P-102 188.7 410 78.1 ELEVATED`<br>`P-103 92.0 150 45.0 STANDBY` | Exact match to reference | 0 / 0 / 0; **0** | 0.00% | 0.0000 | 1,900.49 ms |
| Scanned turbine inspection PDF | `SOVEREIGN POWER SYSTEMS - FIELD INSPECTION LOG`<br>`ASSET: STEAM TURBINE UNIT 4`<br>`DATE: 2026-10-15`<br>`INSPECTOR: ID-7742`<br>`BEARING VIBRATION: 2.4 MM/S`<br>`EXHAUST PRESSURE: 0.08 BAR`<br>`MAINTENANCE ACTION ITEMS:`<br>`1. REPLACE HYDRAULIC FILTER HF-402 AT 12000 HOURS`<br>`2. CALIBRATE GOVERNOR SENSOR GS-12`<br>`3. RE-TORQUE CASING BOLTS TO 450 NM`<br>`OVERALL STATUS: ACCEPTABLE` | `SOVEREIGN POWER SYSTEMS - FIELD INSPECTION LOG`<br>`ASSET: STEAM TURBINE UNIT 4`<br>`DATE: 2026-10-15`<br>`INSPECTOR ID-7742`<br>`BEARING VIBRATION: 2.4 MM/S`<br>`EXHAUST PRESSURE 0.08 BAR`<br>`MAINTENANCE ACTION ITEMS`<br>`1. REPLACE HYDRAULIC FILTER HF-402 AT 12000 HOURS`<br>`2. CALIBRATE GOVERNOR SENSORS GS-12`<br>`3. RE-TORQUE CASING BOLTS TO 450 NM`<br>`OVERALL STATUS ACCEPTABLE` | 1 / 3 / 9; **13** | 3.83% | 0.1000 | 3,533.35 ms |

The per-fixture paired baseline-prompt vs strict-prompt comparison (no resize) showed:

| Fixture | Baseline CER | Candidate CER | Baseline → candidate WER | Observation |
|---|---:|---:|---:|---|
| Clean plate | 9.24% | 3.36% | 0.1667 → 0.2778 | Character errors fell; punctuation/spacing changes increased word errors. |
| Ambiguous tag | 22.22% | **24.44%** | 1.0000 → 1.0000 | Candidate regressed on this fixture; tag remains unreliable. |
| Pump table | 726.92% | 0.00% | 7.2000 → 0.0000 | Baseline returned verbose JSON with bounding boxes; candidate transcribed the table. |
| Scanned PDF | 3.83% | 3.83% | 0.1000 → 0.1000 | No measured character or word error change. |

The paired overall candidate (no resize) macro CER was 7.91%, matching the earlier live report's aggregate; the per-case ambiguous-tag error was 24.44%. Adding 2x Lanczos preprocessing only for source images with maximum dimension ≤600 px yielded paired macro CER **4.71%**, micro CER **3.32%**, and WER 0.3167; it improved the clean plate versus the no-resize candidate, retained the exact table result, and did not improve the ambiguous-tag recognition enough for dependable serial use. The current official live report independently reran the four fixtures and reported the same macro/micro scores but slightly different individual prediction/latency for the clean plate, illustrating that these are live model results.

An experiment that upscaled every fixture globally is preserved in [ocr_preprocessing_comparison.json](ocr_preprocessing_comparison.json) and was rejected: macro CER rose to 31.83%, micro CER to 57.35%, keyword recall fell to 0.50, the table regressed, and the two PDF page requests returned HTTP 400. Latency comparisons are not treated as a gain; cache and run order were not controlled sufficiently for that inference.

**Annotation issue:** The PDF ground-truth keyword list includes `TG-UNIT-4`, but the reference transcription and fixture say `STEAM TURBINE UNIT 4`. The reference/keywords were left untouched. This inconsistency can affect keyword-recall interpretation; the PDF's 0.875 keyword recall must be read with that caveat.

## Air-gap, security, and runtime boundaries

The six checks passed: application-level egress interception, source URL audit, sandbox profile, secret/Git hygiene, Compose profile, and serialization/AST safety. The verifier emitted an intentional blocked-request diagnostic and explicitly warns that OS firewall rules are required for full isolation. The source check found only loopback service endpoints in app/frontend source; package lockfiles still refer to the npm registry for dependency installation. No packet capture, host firewall policy validation, clean offline installation, or full external-egress penetration test was performed. Do not infer complete air-gap operation from the 6/6 application verifier result.

## Working tree, changes, and preservation

Branch is `main`, HEAD is `07b5089`; no files were staged or committed during this audit. The working tree was already dirty. Existing frontend work in `frontend/src/App.tsx`, `frontend/src/components/CitationInspectorDrawer.tsx`, and `frontend/src/components/KnowledgeHub.tsx` remains in place; the production build and frontend lint pass with it. No frontend file was modified by the OCR experiment.

Tracked modified files at audit close:

```text
.env.example
README.md
app/agent/graph.py
app/knowledge/ocr/vision_engine.py
app/routing/service.py
docker-compose.yml
frontend/src/App.tsx
frontend/src/components/CitationInspectorDrawer.tsx
frontend/src/components/KnowledgeHub.tsx
scripts/start_workbench.ps1
scripts/verify_airgap.py
scripts/verify_real_application.py
tests/test_agent/test_graph.py
tests/test_knowledge/test_ocr.py
tests/test_routing/test_waterfall_router.py
```

Untracked project files include the controlled synthetic evaluation data and fixtures, evaluation metrics/runners/tests, and saved reports under `eval/`, plus `scripts/compare_ocr_prompt_variants.py`, `scripts/generate_synthetic_eval_fixtures.py`, `scripts/run_held_out_routing_eval.py`, `scripts/run_quantitative_eval.py`, and the three `tests/test_eval/` modules. The individual report artifacts are linked above. Pytest temporary directories created for the final runs under `eval/` were removed after testing.

The verification scripts use fixed paths under `eval/fixtures/` and validated synthetic fixture manifests. The live acceptance record names a controlled generated turbine specification. Inspection found no personal-directory scanning in the evaluation runner or verifier. The audit did not ingest or evaluate private user documents.

## Checks not performed and remaining limitations

- Docker daemon was unavailable, so Docker-backed sandbox behavior and actual compose startup were not tested.
- Browser UI was not driven through login; only the app sign-in page rendered in the browser check. The separate live acceptance record verifies API-level login and workflows.
- The browser-only UI check was intentionally done with Vite running but API backend absent; the page displayed API and pgvector unreachable. It is not evidence against the separately recorded API acceptance run.
- No exhaustive tests were performed for streaming interruption/cancel, service restart/persistence recovery, production database migrations/backup, malformed or oversized upload matrices, TOTP enrollment/recovery lifecycle, concurrent multi-user load, long-duration operation, host firewall behavior, or offline dependency/model provisioning.
- Real industrial serial OCR is not ready for unattended decisions: the ambiguous tag scored 13.33% CER, WER 1.0, and zero keyword recall in the final live report.
- The refusal-phrase integration test failed once on a live model and passed twice afterward (isolated and in the confirmatory full suite). Its wording-based result is model-dependent; do not label the full test suite universally deterministic.
- Quantitative live evaluation in the report covers OCR only. Routing, retrieval, grounding/citation and deterministic-tool tables show zero evaluated cases / skipped in that evaluation report; their zero metric fields are not measured failures or passes. Separate live acceptance exercised one retrieval/citation scenario.

## Readiness assessment

**Controlled academic demonstration — GO.** Use the provided synthetic fixtures, a local model already installed, and the documented controlled workflow. Present the successful citation run along with the preserved failed citation run and OCR limitations. Treat generated engineering answers as demonstrative, not operational instructions.

**Real industrial deployment — NO-GO.** The evidence does not establish production reliability, complete network isolation, validated Docker sandbox enforcement, lifecycle/recovery readiness, operational security certification, or acceptable OCR accuracy for critical identifiers. Require site-specific security/firewall validation, Docker/runtime verification, operational testing, human review controls, and a more reliable serial-tag OCR workflow before deployment.

## Targeted post-audit verification — 2026-10-25

This section supersedes the earlier statements above that the browser workflow had not been driven. The older saved acceptance logs remain unchanged: `live_e2e_acceptance.log` is the failed citation run and `live_e2e_acceptance_final.log` is the successful API acceptance record. Browser attempts are separately preserved under `eval/post-audit-2026-10-25/` and are not folded into either API log.

### Real browser UI evidence

Chrome was driven through the UI using Playwright Core and a real Chrome executable (`C:\Program Files\Google\Chrome\Application\chrome.exe`). The browser script was `node eval\post-audit-2026-10-25\browser_acceptance.cjs` with `PLAYWRIGHT_CORE`, `CHROME_EXE`, synthetic analyst/admin password environment variables, and `BROWSER_ATTEMPT` set for each isolated run. The run database and workspace were the dedicated synthetic-only SQLite paths in `eval\post-audit-2026-10-25\`.

The latest complete machine-recorded browser run is `browser_acceptance_results_final.json` / `attempt6-browser-*.png`: **11 checks passed and 2 failed of 13**. Browser UI checks passed for page/health rendering, login, synthetic upload, Knowledge Hub chunk inspection, retrieval query, agent answer with grounded citation, citation inspector, citation-to-Knowledge-Hub navigation, XLSX generation, XLSX download (4,797 bytes), and no uncaught page errors. Its DOCX generation check failed because no expected DOCX appeared in the artifact list; the DOCX download then failed because the artifact was absent. This is a browser-driven failure, not an API-only inference.

Earlier browser attempt 5 (`browser_acceptance_attempt5.json`) passed DOCX and XLSX generation in the agent UI, but the script stopped on a cancelled DOCX download. The generated DOCX is present in that isolated workspace as `workspace/session_sjqsv80/browser_demo_report.docx` (36,703 bytes). An authenticated API diagnostic returned HTTP 200 for that DOCX, but it is **not** evidence of a browser download. Attempt 6 exposed the frontend download issue for XLSX and passed after the authenticated blob-download change in `frontend/src/api/client.ts` and `frontend/src/App.tsx`; its DOCX could not exercise that path because DOCX generation failed first. Therefore the browser-driven DOCX generation-and-download workflow remains **not passed end to end**. The current browser UI diagnosis also returned `Validation failed: 'content' parameter is required and cannot be empty for doc_gen` after the model attempted the tool; repeated tool errors were visible in the UI. Do not hide this failure behind the earlier successful API record.

Attempt records 1–6 and their screenshots are retained as separate evidence, including earlier selector/modal issues and first-run failures. `browser_acceptance.cjs` now saves each new run under its attempt-specific filename and records a DOCX retry separately; that revised retry branch has not yet been executed. Browser checks are distinguished from the API acceptance log above.

### Docker sandbox and host network boundary

**Docker runtime sandbox: NOT VERIFIED.** The exact commands `docker version` and `docker info --format '{{.ServerVersion}}'` reported Docker client 29.7.2 but could not connect to `npipe:////./pipe/dockerDesktopLinuxEngine` because the named pipe does not exist. No real container sandbox test ran. The earlier 4 passing sandbox tests are mocked/unit tests only. In particular, allowed/denied execution, filesystem boundary enforcement, timeout, resource limits, runtime cleanup, daemon failure, and image-pull/image-missing behavior were not verified against a live Docker daemon. No fail-closed behavior was changed to manufacture a pass.

**Host/container egress isolation: NOT ESTABLISHED.** Read-only `Get-NetFirewallProfile | Select-Object Name,Enabled,DefaultInboundAction,DefaultOutboundAction` showed Domain, Private, and Public profiles enabled with inbound/outbound actions `NotConfigured`. The controlled, no-payload command `curl.exe --max-time 8 -sS -o NUL -w "HTTP=%{http_code} REMOTE_IP=%{remote_ip}\n" https://example.com` reached **HTTP 200** at `172.66.147.243`; this is direct evidence that the host could reach public HTTPS at the time tested. Compose declares its default network `internal: false` (`docker-compose.yml`), and no host-wide or live-container isolation policy was proven. `DockerSandbox` requests `network_mode="none"`, but Docker was unavailable, so that control remains source-level configuration only. The six air-gap verifier checks are application/source/profile checks; they do not establish host or live-container isolation. No firewall settings or protections were changed.

### Refusal-test variability and OCR experiment

The exact command below was run four times, serially, with `OLLAMA_NO_CLOUD=1` and the existing local model-backed test database:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_integration\test_real_agent_workflow.py::test_real_agent_insufficient_evidence_refusal -q -ra --basetemp=eval\.refusal-repeat-N
```

Results were **pass, pass, pass, fail**. The failure was at the substring-based `evidence_missing_indicators` assertion. A temporary diagnostic print was added for one further run and then removed; that run passed the assertion, but its response said no information was found and then invented `[Source: Cryogenic_Tank_Operating_Manual.pdf]` even though no documents were retrieved. The deterministic validator appended an “Ungrounded Citation & Evidence Warning.” The exact response is in the command output for this audit turn, not in a separate persistent response log. Thus the failure's exact response was not captured and its precise wording cause is unconfirmed; the test is demonstrably intermittent, and the diagnostic pass exposes a source-hallucination risk the current exact-filename assertion does not catch. The diagnostic print was removed; no test logic was changed.

The serial tag was re-evaluated with the **same unchanged synthetic image, ground-truth transcription, model (`qwen3.5:4b`), prompt, temperature 0, `num_predict=1024`, and `think=false`** for every candidate. The script and complete output are `eval/post-audit-2026-10-25/ocr_ambiguous_variants.py` and `ocr_ambiguous_variants.json`. Current 2x Lanczos returned 6 edits, CER 13.33%, WER 1.0, 1,466.61 ms. The single 4x nearest-neighbor candidate returned 3 substitutions, 0 deletions, 0 insertions, CER 6.67%, WER 1.0, 2,540.55 ms. Other candidates: 4x Lanczos 5 edits / 11.11% CER; autocontrast+sharp 2x and pixel-segmented lines 4x each 6 edits / 13.33%. The 4x nearest-neighbor result is a **single-run experiment only**: both second-line `C`/`O` and third-line `C`/`O` substitutions remain, WER is still 1.0, and no production OCR code or ground truth was changed. It is not a validated accuracy gain and should not be used to identify serials without human confirmation.

### Regression check, changes, and evidence limits

After the authenticated browser download implementation, `frontend/npm run build` and `frontend/npm run lint` passed; `pytest tests\test_artifacts -vv -ra --basetemp=eval\.post-audit-artifacts-temp2` passed **7 tests**. XLSX generation and browser download passed in attempt 6. The unresolved DOCX agent-tool failure means the whole browser deliverable flow is not green. The earlier full pytest/Ruff/Mypy results remain those recorded in the first half of this report; no fresh full-suite run was performed during this targeted pass. The exact targeted Docker runtime tests, DOCX complete browser flow, deterministic capture of the refusal test's failing model response, repeat OCR validation, and live host/container isolation remain unverified or blocked as explicitly described above.

Files added/changed by this targeted pass include the attempt-specific evidence and OCR experiment under `eval/post-audit-2026-10-25/`, this report, and the authenticated artifact download handling in `frontend/src/api/client.ts` and `frontend/src/App.tsx`. Existing frontend modifications were preserved. Git status was reviewed; no files were staged, committed, reset, or pushed. Existing failed and successful acceptance logs were not edited. Verification inputs were fixed synthetic fixtures under `eval/fixtures/`; no personal directories were scanned and no private user documents were ingested. Temporary pytest basetemp directories were removed after the runs.

### Updated readiness decisions

**Academic demo — GO WITH DISCLOSED LIMITS.** The browser has demonstrated login, synthetic upload, Knowledge Hub inspection, RAG retrieval, grounded citation inspection/navigation, and XLSX generation/download. A successful API acceptance record is preserved. DOCX UI generation remains model-dependent and failed in the latest browser run; show the failure honestly and do not promise an uninterrupted DOCX demo.

**Controlled synthetic-data testing — GO WITH CONTROLS.** Keep the environment local, use only fixed synthetic fixtures, retain human review for generated content and OCR identifiers, and do not interpret the app-level verifier as network isolation. Docker sandbox enforcement is unverified and must remain fail-closed.

**Real confidential industrial data — NO-GO.** Public HTTPS egress succeeded, Docker runtime isolation was unavailable for verification, DOCX generation and refusal behavior remain variable, and the ambiguous serial-tag OCR still has 6.67% CER / WER 1.0 in the best single-run candidate. Site-approved egress controls, live Docker enforcement tests, stronger grounding/refusal validation, repeat OCR evaluation, and operational/security review are blockers.

## Completion repair and final regression follow-up — 2026-10-26

The following evidence supersedes the previous DOCX browser-failure status and the earlier test totals for the current working tree. Historical acceptance logs and failed-run records above remain intact and separate.

### Repairs

- Added a fail-closed, exact-evidence fallback in `app/agent/citation_validator.py` and `app/agent/service.py`: if a model answer fails citation checks, the system may show a query-matched sentence copied verbatim from structured RAG results, with that result's source filename, only after the fallback itself passes citation validation. It never creates fallback evidence from non-RAG tool output. The response includes `evidence_fallback_used`; when auditing is active, rejected model-response flags are recorded.
- Tightened the reasoning prompt to ask for concise source-close RAG responses and removed the inaccurate system claim that the deployment is already air-gapped.
- Corrected an integration test to resolve generated files relative to configured `WORKSPACE_DIR`, so the suite can run without writing into the normal user workspace. Tightened its synthetic temperature expectation to exact `78.5` rather than accepting the distinct 80 C trip threshold.
- Corrected the browser acceptance harness's XLSX prompt and artifact-row selector. The selector now checks the Download link in the exact file row, eliminating a false selection of the DOCX link.
- Resolved Ruff errors found during the final checks, including an unused OCR experiment import and CLI print lint annotations.

### Final current-tree evidence

| Check | Result | Command / evidence |
|---|---|---|
| Full pytest | **291 passed, 1 skipped, 0 failed, 292 collected; 84.41 s** | `.venv\Scripts\python.exe -m pytest -o 'addopts=--tb=short' -q -ra --basetemp=eval\.completion-full-tests-final-2026-10-26` with local Ollama (`OLLAMA_NO_CLOUD=1`) and isolated synthetic SQLite/workspace. Only skip: Windows symlink creation blocked at `tests/test_tools/test_adversarial_security.py:71`. |
| Focused citation, DOCX and service tests | **28 passed** | `.venv\Scripts\python.exe -m pytest tests\test_citation_validator.py tests\test_tools\test_doc_gen_contract.py tests\test_agent\test_service.py -q -ra --basetemp=eval\.completion-core-final-2026-10-26` |
| Live model RAG check | **4 of 4 repeated runs passed after the fallback change** | `tests\test_integration\test_real_agent_workflow.py::test_real_agent_grounded_rag_workflow`, each with a separate `eval\.completion-rag-fallback-repeat-N` basetemp. Before this change, relevant retrieved evidence was available but model citations intermittently failed the lexical screen and the sanitizer correctly abstained; prompt-only wording change did not resolve it. |
| Browser acceptance | **13/13 passed** | Authoritative clean-stack Chrome/Playwright run: `eval/post-audit-2026-10-26-completion/browser_acceptance_verified-final-explicit-docx-2026-10-26.json`, with attempt-specific screenshots. Passed login, synthetic upload, Knowledge Hub, RAG, citation inspection/navigation, DOCX and XLSX generation/download, and no page errors. Backend startup log confirms it initialized the fresh `acceptance-final.sqlite3` database. |
| DOCX download/content | **Pass** | Browser download 36,828 bytes; `python-docx` parsed three paragraphs and confirmed 450 Nm/source text. `eval/post-audit-2026-10-26-completion/downloads/browser_demo_report.docx`. |
| XLSX download/content | **Pass** | Browser download 5,131 bytes; `openpyxl` parsed sheet `Synthetic Turbine Metrics` and the expected torque/source row. `eval/post-audit-2026-10-26-completion/downloads/browser_demo_metrics.xlsx`. Both captured authenticated artifact GETs returned HTTP 200. |
| Ruff / Mypy | **Pass** | `.venv\Scripts\ruff.exe check .` — all checks passed. `.venv\Scripts\mypy.exe app` — no issues in 74 source files. |
| Frontend | **Pass** | From `frontend/`: `npm run build` (TypeScript + Vite, 1,938 modules) and `npm run lint`. |
| Application offline verifier | **6/6 pass** | `.venv\Scripts\python.exe scripts\verify_airgap.py`. This is an application/source/profile verifier, not host or container isolation evidence. |
| Docker runtime | **Blocked / not verified** | Rechecked `docker context ls`, `docker version`, `docker info --format '{{.ServerVersion}}'`; client 29.7.2, but `npipe:////./pipe/dockerDesktopLinuxEngine` is missing. No real sandbox test ran. |
| Host/container network isolation | **Not established** | Prior controlled `https://example.com` returned HTTP 200; Compose default network remains `internal: false`; no OS/firewall/live-container isolation proof. |

Additional records and artifact outputs are under `eval/post-audit-2026-10-26-completion/`. This includes separate pytest basetemps (including failed diagnostic attempts), browser JSON/screenshots, parsed downloads, isolated DB/workspaces and process logs. The failed initial service startup is separately preserved under `failed-start-logs/`; it is not included as successful acceptance evidence.

**Verification provenance correction:** `browser_acceptance_completion-final-2026-10-26.json` was captured before the latest source was loaded and is retained but not used as current-code evidence. Only the earlier project test processes were stopped; unrelated Docker Desktop/WSL relay processes were left running. The backend that produced the authoritative run started at 15:50 local time on 2026-10-26, initialized `acceptance-final.sqlite3`, and logged successful requests for both final artifact downloads. Its first UI attempt generated a valid DOCX but chose a model-derived filename, failing the harness's requested-filename assertion. After the harness prompt was changed to specify the full `doc_gen` JSON object, `browser_acceptance_verified-final-explicit-docx-2026-10-26.json` passed all 13 checks. The intermediate failed result remains separately preserved.

No files were staged, committed, reset or pushed. Existing frontend modifications were preserved. Verification used only the fixed synthetic corpus at `eval/fixtures/corpus/turbine_operating_manual.txt` and an isolated SQLite database/workspace. No personal-directory scan or private document ingestion was performed.

### Updated readiness

**Academic demo with synthetic data — GO with disclosed limits.** The latest browser run covers end-to-end DOCX/XLSX generation and downloads, and the current Python suite passes apart from the symlink-permission skip. Keep local models available, disclose prior failed evidence and current OCR limits, and use human review.

**Controlled synthetic-data testing — GO with controls.** Use isolated data paths and local models. The fallback returns a verifiable excerpt rather than presenting an invalid model answer as grounded; it is not proof of semantic entailment or general reliability.

**Real confidential industrial data / production — NO-GO.** Docker runtime isolation and host/container egress controls are still unverified. Earlier host HTTPS access succeeded, OCR identifiers remain unreliable, and backup/recovery, load and operational security controls need evidence. No “fully air-gapped” or production-certified claim is justified.

## Docker Desktop runtime verification and repair — 2026-10-26

This section supersedes the earlier “Docker runtime blocked / not verified” status above. It does not supersede the host-egress finding: host-level isolation remains unestablished.

### Commands and environment

Docker Desktop was started by the user. An initial call from the restricted shell showed `permission denied` for `npipe:////./pipe/dockerDesktopLinuxEngine`; the same read-only Docker commands were then run with approved elevated access to the Docker named pipe. They reported Docker Engine **29.7.2**, Linux `x86_64`, and a pre-existing local `python:3.11-slim` image. No project service, unrelated container, or firewall setting was changed. No image was pulled for the successful sandbox runs.

```powershell
docker context ls
docker version
docker info --format '{{.ServerVersion}} {{.OperatingSystem}} {{.OSType}} {{.Architecture}}'
docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}}'
.venv\Scripts\python.exe scripts\verify_docker_sandbox_runtime.py
.venv\Scripts\python.exe -m pytest tests\test_sandbox\test_docker_sandbox.py -q --basetemp=eval\.docker-sandbox-unit-final2
.venv\Scripts\ruff.exe check app\sandbox\docker_sandbox.py tests\test_sandbox\test_docker_sandbox.py scripts\verify_docker_sandbox_runtime.py
```

The live harness uses only short synthetic Python snippets, a fresh per-run session under `eval/post-audit-2026-10-26/docker-sandbox-workspace/`, a literal public-IP connectivity probe from the sandbox, and a nonexistent image addressed only to loopback `127.0.0.1:1`. It does not inspect personal directories or open user documents. The authoritative final 12/12 run record is `eval/post-audit-2026-10-26/docker_sandbox_runtime.json`; the repeatable harness is `scripts/verify_docker_sandbox_runtime.py`.

### Initial defect and repair

The first genuine container run passed 8/11 harness checks and exposed a real security defect: `python:3.11-slim` defaulted to root because `DockerSandbox.execute()` did not pass a user. The live inspect showed an empty `Config.User`; inside that container `os.setuid(0)` succeeded and `/etc/shadow` was readable. The captured failure is retained in `eval/post-audit-2026-10-26/docker_sandbox_runtime_initial_root_failure.json`. The sandbox already set `network_mode=none`, dropped all capabilities, applied `no-new-privileges`, and enforced the configured memory/CPU/PID limits, but those controls did not replace a non-root identity.

`app/sandbox/docker_sandbox.py` now passes `user="1000:1000"`, consistent with its existing security intent. `tests/test_sandbox/test_docker_sandbox.py` now asserts that argument. Documentation was also changed to say the sandbox container has no network attachment, avoiding a claim of host-level air-gapping.

### Final live Docker results

The final clean-session run passed **12/12** checks:

| Behavior | Live result |
|---|---|
| Allowed execution | Synthetic arithmetic/file operation completed; output was verified in the mounted session workspace. |
| Filesystem boundary | Inspection showed the only bind mount was the selected session directory at `/workspace`; a separate container-local `/tmp` write did not create the corresponding host path. Invalid traversal session ID was rejected before container launch. |
| Denied operations | As UID `1000:1000`, `setuid(0)` and reading `/etc/shadow` both raised `PermissionError`; a direct connection to `1.1.1.1:443` failed inside the `network_mode=none` container. |
| Resource settings | Live container inspection confirmed memory `536870912` bytes, `NanoCpus=2000000000`, and `PidsLimit=50`. These values were inspected; no memory-exhaustion stress test was run. |
| Other runtime controls | Inspection confirmed `NetworkMode=none`, `CapDrop=["ALL"]`, `no-new-privileges:true`, and user `1000:1000`. |
| Timeout and cleanup | An infinite loop with a 2-second timeout was reported timed out and killed; inspection confirmed that both the timed-out container and successful container were removed after execution returned. |
| Daemon failure behavior | Without stopping Docker Desktop, the SDK's ping-failure path was exercised against loopback port 1. It returned “Docker daemon is unavailable” and “Execution blocked (fail-closed)”; no host execution occurred. This is a simulated daemon failure, not a test that stopped the live service. |
| Missing image behavior | A deliberately nonexistent image at `127.0.0.1:1` failed with a registry connection refusal and `success=false`, `exit_code=-1`. The request was directed only to loopback; no external registry was contacted and no fallback execution occurred. |

The first post-repair rerun reused the session directory written during the initial root-container run; its workspace write failed. That result is retained in `eval/post-audit-2026-10-26/docker_sandbox_runtime_reused_workspace_failure.json`. The final harness now creates a unique clean synthetic session on every run, and the fresh-session run passed. Existing workspace files were not changed or recursively repaired. Review permissions of any pre-existing workspace output before reusing it under the new non-root identity.

The four existing mocked sandbox unit tests passed (**4 passed**), and targeted Ruff passed. The complete 291-test suite was not rerun after this narrowly scoped Docker change. No full-suite regression claim is made for the change; relevant sandbox unit and live runtime checks passed.

### Updated readiness after live sandbox tests

**Academic demonstration with synthetic data — GO with disclosed limits.** The sandbox's actual Docker runtime controls have now been exercised alongside the prior browser acceptance evidence. Continue to disclose OCR/model variability and the current deployment limitations.

**Controlled synthetic-data testing — GO with controls.** Docker sandbox behavior is verified on this Docker Desktop/Linux engine for the tested image and configuration. Keep workspaces isolated, review legacy workspace permissions, and retain human review of generated answers and OCR identifiers.

**Real confidential industrial data / production — NO-GO.** This verifies the code-execution container controls only. The host can reach public HTTPS; Compose's ordinary service network is not configured as internal; host-wide egress isolation, complete deployment security, production operations, OCR reliability for identifiers, and operational recovery remain unproven. Do not describe the whole application as air-gapped or production-certified.

No files were staged, committed, reset, or pushed. Existing frontend changes, previous audit logs, and acceptance records remain preserved.

## GitHub publication preflight — 2026-10-26

The latest full-suite attempts were run after the Docker non-root repair. With Ollama unavailable, the first completed attempt ended **275 passed, 15 skipped, 2 failed** in 78.73 seconds. Both failures were model-dependent integration workflows that could not connect to Ollama. After the Ollama CLI listed the installed models, the Python HTTP endpoint `127.0.0.1:11434` still refused connections; the second completed suite ended **279 passed, 12 skipped, 1 failed** in 131.40 seconds. Its failure was `tests/test_integration/test_real_ollama.py::test_real_ollama_health_and_list`.

These are actual failed preflight runs, not passing evidence. They do not demonstrate a Docker non-root regression: the Docker-specific four unit tests passed, the live Docker harness passed 12/12, and the app/browser build, Ruff, and Mypy checks passed. The prior saved model-enabled full-suite run recorded 291 passed, 1 skipped, 0 failed before the final Docker non-root change. No newer clean full-suite result could be obtained because the Ollama HTTP service was unavailable. The exact commands were:

```powershell
$env:OLLAMA_NO_CLOUD='1'
.venv\Scripts\python.exe -m pytest -o 'addopts=--tb=short' -q -ra --basetemp=eval\.push-validation-admin-2026-10-26
$env:OLLAMA_NO_CLOUD='1'
.venv\Scripts\python.exe -m pytest -o 'addopts=--tb=short' -q -ra --basetemp=eval\.push-validation-ollama-2026-10-26
```

An earlier restricted-runner attempt using `--basetemp=eval\.push-validation-2026-10-26` stalled against the unavailable local service and was interrupted without producing a result; it is not counted as a completed test run. No test changes were made to disguise unavailable model dependencies.
