# Current Project Status — Sovereign On-Premise Agentic AI Workbench

**Audit date:** 2026-10-25 (Asia/Calcutta)<br>
**Workspace:** `D:\AGENTIC AI MAJOR PROJECT`<br>
**Repository:** `SurajN4ir/Agentic-AI-Workbench`<br>
**Audited HEAD:** `main` at `07b50896fd89fa8923fa4c94ce684f7d1f2d0541`<br>
**Method:** Read-only inspection of the current checkout, Git metadata, current code, saved test/evaluation reports, logs, browser JSON and screenshots. No tests were run for this status audit. The saved reports predate some current uncommitted code; they are evidence of those runs, not proof that every current diff has been revalidated.

## 1. Executive summary

This is a substantial working academic prototype: the React UI and FastAPI service are connected to a LangGraph agent, local Ollama models, document ingestion and retrieval, user authentication, administrative controls, audit records, artifact generation, and an optional Docker code sandbox. Saved evidence supports meaningful synthetic-data end-to-end behavior, including browser login, upload, RAG, citation inspection/navigation and XLSX generation/download. The most recent API acceptance log separately reports a successful citation and DOCX download.

It is **not complete as an end-to-end product**. The latest full browser run reports 11/13 checks, with DOCX generation and download failing; the prior browser attempt also did not finish a DOCX browser download. A different earlier API acceptance run generated a response with no verified citation despite printing an overall success banner. Docker runtime isolation was not exercised because the Docker daemon was unavailable. Host egress isolation was not demonstrated; a prior controlled request to `example.com` succeeded. OCR errors on ambiguous serials are material, and the best reported preprocessing result is one experimental inference, not a repeatable improvement.

**Readiness:** academic demonstration with synthetic data: **GO with disclosed limitations**; controlled local synthetic-data testing: **GO with controls**; confidential industrial data and production deployment: **NO-GO** on the available evidence. The engineering completion estimate is **about 65–75%**, not a measured score. Strong feature breadth and test coverage are offset by unresolved reliability, security-boundary, deployment and browser-workflow evidence.

## 2. Current repository and Git state

- Current directory and repository root: `D:/AGENTIC AI MAJOR PROJECT`.
- Branch: `main`; HEAD: `07b5089` (`fix(security): harden synthetic verification and fail-closed tests`). Recent commits include acceptance and browser/download work. The configured remote is `origin` at the stated GitHub repository.
- `git rev-list --left-right --count HEAD...origin/main` returned `0 0`: at the time of inspection, local HEAD and the existing local `origin/main` ref were equal. This uses local Git metadata; no fetch or remote network check was performed.
- Working tree is **modified**. There are 23 modified tracked files, no staged changes reported, and 23 top-level untracked entries (111 leaf paths under those entries, including generated test DOCX outputs). `git status --ignored --short` also shows local `.env`, databases, uploads, workspace files, logs, build output, dependency/cache directories and other ignored runtime data. Their contents were not read for secrets or personal documents.
- No reset, stage, commit, push or revert was performed. Existing changes remain as found. In particular, the frontend edits remain in `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/components/CitationInspectorDrawer.tsx`, and `frontend/src/components/KnowledgeHub.tsx`.

### Modified tracked files

`.env.example`; `README.md`; `app/agent/citation_validator.py`; `app/agent/graph.py`; `app/agent/prompts.py`; `app/agent/service.py`; `app/knowledge/ocr/vision_engine.py`; `app/routing/service.py`; `app/tools/registry.py`; `docker-compose.yml`; `frontend/src/App.tsx`; `frontend/src/api/client.ts`; `frontend/src/components/CitationInspectorDrawer.tsx`; `frontend/src/components/KnowledgeHub.tsx`; `scripts/start_workbench.ps1`; `scripts/verify_airgap.py`; `scripts/verify_real_application.py`; `tests/test_agent/test_graph.py`; `tests/test_agent/test_service.py`; `tests/test_citation_validator.py`; `tests/test_integration/test_real_agent_workflow.py`; `tests/test_knowledge/test_ocr.py`; `tests/test_routing/test_waterfall_router.py`.

### Important locally untracked project and evidence files

- `app/tools/doc_gen_validation.py` and `tests/test_tools/test_doc_gen_contract.py` (DOCX input contract work).
- New evaluation code/data: `eval/quantitative_metrics.py`, `scripts/run_quantitative_eval.py`, `scripts/run_held_out_routing_eval.py`, `scripts/generate_synthetic_eval_fixtures.py`, `scripts/compare_ocr_prompt_variants.py`, `tests/test_eval/`, `eval/dataset/`, and controlled files under `eval/fixtures/`.
- `eval/reports/` and `eval/post-audit-2026-10-25/` contain acceptance logs, JSON reports, browser scripts/results/screenshots, OCR experiments, run databases, and process/runtime logs. These have not been added to Git and include ephemeral evidence and generated files. Keep them until deliberately reviewed and classified; do not assume they are disposable.
- Several untracked `eval/.priority12-*` and `eval/.docgen-tests` directories contain pytest outputs, including generated DOCX files. These are also current local artifacts, not tracked source.

### Incomplete-work search

A bounded `rg` scan of `app`, `frontend/src`, `scripts`, and `eval` found ordinary `pass` statements in exception handling/abstract interfaces and a deterministic mock provider used by benchmark paths. It did not establish a comprehensive TODO inventory; generated data and normal UI placeholders make simple text search noisy. No source-wide completion claim follows from that scan.

## 3. Architecture overview

The actual system is a React 19 / TypeScript / Vite SPA served by FastAPI in local development or a frontend container. FastAPI exposes identity, knowledge, agent, tool/artifact, audit and benchmark APIs. An agent workflow routes a request, uses LangGraph state and a bounded tool loop, calls Ollama through the model provider, and can retrieve indexed document chunks. SQLAlchemy models support SQLite for local/test use and PostgreSQL/pgvector in Compose. Files are stored in a validated workspace/session path. Optional code execution requests a constrained Docker container and is intended to fail closed when Docker is unavailable.

The architecture is implemented in code, but runtime guarantees depend on environment. `app/network/offline_guard.py` blocks selected Python `urllib` requests at application level; it explicitly cannot constrain subprocesses/native networking and requires OS/container controls for true isolation. `docker-compose.yml` exposes local port bindings but its default bridge has `internal: false`. Docker sandbox settings are visible in source, yet the daemon was unavailable in the reported runtime check. Thus the implementation has offline-minded controls, not demonstrated host-wide air-gap enforcement.

### Major source map

| Area | Main implementation |
|---|---|
| Startup/config/database | `app/main.py`, `app/config.py`, `app/database.py`, `alembic.ini`, migrations directory |
| Identity/RBAC/audit | `app/identity/{router,service,dependencies,models}.py`, `app/audit/{service,models}.py`, `scripts/setup_admin.py` |
| SPA and navigation | `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/components/KnowledgeHub.tsx`, `CitationInspectorDrawer.tsx`, `BenchmarkDashboard.tsx` |
| Routing/agent | `app/routing/{router,service,classifier,keyword_check,metadata_check}.py`, `app/agent/{router,graph,service,state,parser,prompts}.py` |
| Model providers | `app/models/{base,ollama,registry,schemas}.py`; local Ollama configuration is in `.env.example` and Compose |
| Knowledge/OCR | `app/knowledge/{router,service,chunking,models}.py`, `app/knowledge/parsers/`, `app/knowledge/ocr/` |
| Tools and deliverables | `app/tools/{registry,router,math_eval,spreadsheet,file_io,doc_gen_validation}.py`, `app/artifacts/{router,service,generator,models}.py` |
| Sandbox/network controls | `app/sandbox/docker_sandbox.py`, `app/network/offline_guard.py`, `scripts/verify_airgap.py`, `docker-compose.yml` |
| Evaluation and installation | `eval/`, `scripts/`, `tests/`, `README.md`, `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `docs/SECURITY_AUDIT.md` |

## 4. Feature completion matrix

Status meanings: **Verified** means saved direct evidence for intended behavior; **Partially verified** means some scenarios pass but important ones remain; **Implemented, unverified** means code exists without sufficient execution proof; **Blocked** means environment prevents execution; **Broken** means a reproducible failure exists; **Not implemented** means expected behavior is absent.

| Feature | Expected behavior and current implementation | Relevant files / test evidence | Status, limitations, next action |
|---|---|---|---|
| Frontend/navigation | Authenticated SPA with Agent, Knowledge Hub, citation drawer and admin/benchmark surfaces. Browser screenshots show core views and navigation. | `frontend/src/App.tsx`, `KnowledgeHub.tsx`, `CitationInspectorDrawer.tsx`; Playwright results and screenshots under `eval/post-audit-2026-10-25/`. Earlier build/lint claims are in `final_project_audit.md`. | **Partially verified.** Browser acceptance is 11/13; document-generation flow fails for DOCX. Re-run build/lint after current diffs before release. |
| Backend API/startup | FastAPI health/root routes and feature routers; local synthetic stack served the browser run. | `app/main.py`; browser JSON and API acceptance logs. | **Verified** for basic loopback health and tested workflows; **Partially verified** for lifecycle/production deployment. Compose startup was not established. |
| Authentication/account provisioning | Username/password auth, bcrypt hashing, JWT access/refresh handling and optional TOTP; admin is provisioned via interactive script, no universal default password. | `app/identity/`; `scripts/setup_admin.py`; API acceptance log and browser login pass. | **Partially verified.** Login is exercised; TOTP recovery/enrollment, lockout/load, session revocation and production secrets lifecycle are not established by this evidence. |
| Authorization/admin | Role dependencies protect admin and session-artifact operations; saved API acceptance says admin authorization passed. | `app/identity/dependencies.py`, identity/audit routers, tests in `tests/test_identity`, API log. | **Partially verified.** One admin flow is recorded; comprehensive route-by-route authorization proof is not summarized in a current raw report. |
| Agent orchestration | LangGraph route/reason/tool/synthesis flow, bounded iterations, model streaming/tool dispatch. | `app/agent/graph.py`, `state.py`, `service.py`; `tests/test_agent`, `tests/test_integration`. | **Partially verified.** Live answer exercised; refusal wording is model-dependent and fabricated-reference risk was observed in historical diagnostics. Streaming cancel/recovery is unverified. |
| Intent/routing | Keyword, metadata, and classifier routing to task/persona/tool. A held-out report records 35/35 route labels. | `app/routing/`; `eval/reports/held_out_routing_report.{md,json}`; `tests/test_routing`. | **Partially verified.** Held-out examples appear to test routing decisions, not a broad independent deployment distribution; newer routing diffs are uncommitted. |
| Ollama/models | Local provider integrates chat, embeddings and vision inference with named local models. | `app/models/ollama.py`, `app/models/registry.py`, `app/knowledge/ocr/vision_engine.py`; live acceptance and OCR JSON. | **Verified** for specific local-model runs; **Partially verified** across model availability/latency. Earlier offline suite had model-connection failures; no clean offline provisioning proof. |
| Upload/parsing/ingestion | File upload, parsing, chunking and storage with page/sheet metadata. Browser synthetic upload/indexing; API log reports 3 chunks. | `app/knowledge/router.py`, `service.py`, `parsers/`, `chunking.py`; `tests/test_knowledge`; browser evidence. | **Partially verified.** TXT and synthetic PDF/image fixtures covered; malformed/oversize/malicious formats and real industrial corpus are not exhaustively verified. |
| OCR | Tesseract fallback and local vision model/PDF rendering pipeline. | `app/knowledge/ocr/`; `tests/test_knowledge/test_ocr.py`; `final_live_ocr.json`, comparisons. | **Partially verified.** Four fixtures only. Ambiguous serial tag remains unreliable (13.33% live run; 6.67% single experimental variant; WER 1.0). Human verification required. |
| RAG/retrieval | Dense/sparse retrieval and chunk provenance; browser synthetic query retrieved a known 450 Nm fact; API acceptance has one successful retrieval record. | `app/knowledge/service.py`, `chunking.py`, `models.py`; browser JSON; quantitative report. | **Partially verified.** A small controlled corpus and example query pass; broad retrieval is not established. Quantitative report includes small scenario counts and is not a live broad benchmark. |
| Citation integrity/refusal | Validator is intended to match references to retrieved evidence and sanitize unsupported output; current working diff adds stronger provenance checks and abstention sanitization. | `app/agent/citation_validator.py`, `service.py`, `graph.py`; `tests/test_citation_validator.py`; failed/successful API logs. | **Partially verified.** Contradictory historical live results and a diagnostic fabricated-source response remain material. The current validator changes have targeted tests per prior run, but no fresh audit-run or larger adversarial live evaluation. |
| Math/code tools | AST-based math and Docker-only code execution; tool registry applies role policy. | `app/tools/math_eval.py`, `registry.py`, `app/sandbox/docker_sandbox.py`; `tests/test_tools`, `tests/test_sandbox`. | Math: **Partially verified** through unit/integration coverage. Real code sandbox: **Blocked** by missing Docker daemon; mock tests do not establish container isolation. |
| Spreadsheet/document tools | XLSX and DOCX creation from structured inputs and authorized file downloads; new shared DOCX input validator addresses schema mismatch. | `app/tools/doc_gen_validation.py`, `registry.py`, `app/agent/graph.py`, `app/artifacts/`; `tests/test_tools/test_doc_gen_contract.py`; browser attempts. | XLSX: **Verified** in browser generation/download. DOCX: **Broken in latest browser acceptance** (generation absent and download absent), though earlier API log and a prior browser generation artifact exist. Confirm end-to-end after fixing model/tool input and validate downloaded DOCX content. |
| Database/persistence/migrations | SQLAlchemy supports test SQLite and configured Postgres/pgvector; migrations configured. | `app/database.py`, models, `alembic.ini`, `docker-compose.yml`, migration directory. | **Implemented, unverified** for restart, backup/restore, migration upgrade and Postgres production lifecycle. Browser verification used a dedicated SQLite database. |
| Audit/logging | Audit event service/models and security-oriented logging exist. | `app/audit/`, identity and tools; `tests/test_audit`. | **Partially verified.** Presence and test coverage; production retention, immutability and complete secret/content redaction not proven here. |
| Network isolation | Application guard permits loopback and blocks some `urllib` traffic; Docker sandbox requests `network_mode=none`. | `app/network/offline_guard.py`, sandbox, Compose, `scripts/verify_airgap.py`. | **Broken as a claim of host air-gap / Blocked as container verification.** A public HTTPS request previously returned 200; host/container isolation is not established. Keep “application-level offline guard” wording. |
| Streaming/errors/timeouts | SSE/agent workflow and Docker timeout exist. | `app/agent/service.py`, frontend client, sandbox. | **Partially verified.** Agent streaming works in browser; cancellation, reconnect, long-running failures and cleanup under live Docker are unverified. |
| Evaluation/data quality | OCR metrics, route/retrieval/grounding/tool scenarios, held-out routing and controlled synthetic fixtures exist. | `eval/`, `scripts/run_quantitative_eval.py`, `eval/quantitative_metrics.py`, `tests/test_eval/`. | **Partially verified.** OCR has live model evidence; much of other quantitative report is non-live/small-sample. Dataset independence and metric construct validity need review before academic performance claims. |
| Packaging/deployment/docs | Dockerfiles, Compose, setup scripts, README and operational/security docs exist. | `Dockerfile.backend`, `frontend/Dockerfile.frontend`, `docker-compose.yml`, README/docs. | **Partially verified.** Instructions and files exist, but docs contain architecture/model/air-gap claims that differ across documents and exceed proven isolation. Docker stack not run in the current evidence. |

## 5. Test and evaluation evidence reconciliation

### Test results reported previously

`eval/reports/final_project_audit.md` states that a model-enabled full suite collected **276**, passed **275**, failed **0**, and skipped **1** in 56.95 seconds. It attributes the skip to Windows symlink creation restrictions and says 22 tests are under `tests/test_integration/`. That report lists the command:

```powershell
$env:OLLAMA_NO_CLOUD='1'
.venv\Scripts\python.exe -m pytest -o 'addopts=--tb=short' -q -ra --basetemp=eval\.pytest-audit-full-confirm
```

The same report records an earlier no-Ollama run of 259 passed / 2 failed / 15 skipped, and an earlier model-backed run with one refusal assertion failure that passed in subsequent reruns. This status audit did **not** rerun the suite; these are historical report claims, not independently reproduced results for the current dirty tree.

The prior targeted repair pass recorded 5 DOCX contract tests passing; 20 citation + DOCX core tests passing; and a 33-dot focused run across citation, DOCX, service and graph modules exiting successfully. Service-focused tests were run with elevated local socket permission due Windows sandbox event-loop restrictions. The prior turn also recorded four serial runs of the repaired refusal integration assertion passing with local Ollama and `OLLAMA_NO_CLOUD=1`. These targeted-run details are not preserved in a durable test stdout log located during this audit. The historical report's pass/pass/pass/fail refusal repetitions refer to the earlier test version and remain useful evidence of variability, not a contradiction of the later changed test.

The audit report records 44 focused OCR/evaluation tests passing, `ruff check .` passing, `mypy app` passing, `npm run build` and `npm run lint` passing, and six application-level air-gap checks passing. Its commands and summaries are saved in Markdown, but raw command output for every check was not found as an independent transcript. None was rerun in this read-only status pass. The previous targeted pass separately recorded frontend build/lint and seven artifact tests passing after the download change. The current working tree contains subsequent uncommitted changes, so rerun relevant checks before treating those results as current release evidence.

### API acceptance logs — keep separate

- `eval/reports/live_e2e_acceptance.log` (earlier run) shows health, analyst/admin login, upload, retrieval, tool generation, download and path traversal blocking, **but explicitly says `Citations verified: False` and has no verified citations**. Its final “ALL LIVE SYSTEM WORKFLOWS VERIFIED SUCCESSFULLY” banner is inconsistent with its own citation result and must not be treated as an all-green acceptance result.
- `eval/reports/live_e2e_acceptance_final.log` (2026-10-25, isolated temporary SQLite and local Ollama) is a separate successful record. It reports login, synthetic upload/indexing (3 chunks), retrieval (2 chunks), accepted citation, DOCX/XLSX creation, DOCX API download (37,138 bytes), admin access and traversal block. This is API/system-script evidence, **not browser proof**. Preserve both records; the later pass does not erase the earlier failure.

### Browser-driven evidence

Actual Chrome + Playwright UI runs are recorded separately from API tests in `eval/post-audit-2026-10-25/browser_acceptance_*.json` and screenshots.

- `browser_acceptance_results_final.json`, 2026-10-25T06:26:22Z: **11 passed, 2 failed of 13**. Passed: UI/health; browser login; synthetic upload; Knowledge Hub chunk inspection; RAG query; agent 450 Nm answer with citation badge/source; citation inspector; citation navigation; XLSX generation; XLSX browser download (4,797 bytes); no uncaught browser errors. Failed: DOCX generation (artifact absent) and DOCX download (no artifact/empty result).
- `browser_acceptance_attempt5.json`, 06:20:31Z: **10/11 passed**, including DOCX and XLSX generation, but DOCX download was cancelled and no successful browser download was recorded. A DOCX artifact exists and a separate API diagnostic returned 200; neither completes browser download acceptance.
- Later repair attempt `browser_acceptance_repair2026-10-25-1.json`, 08:03:10Z: **5 passed, 4 failed of 9**. Initial login/upload/Knowledge Hub/RAG passed; citation badge and inspector assertions failed because the browser harness expected older UI labels. Screenshots show the citation answer and inspector were visible with new labels; navigation then did not run. This is a harness mismatch/partial attempt, not evidence to replace the latest full result.

Therefore browser login, upload, retrieval, citation inspection/navigation, XLSX and XLSX download have direct browser evidence. DOCX end-to-end browser acceptance remains failed/unverified. Do not merge these browser counts with the separate API script result.

### Quantitative and routing reports

- `quantitative_eval_report.md/json` is dated 2026-10-25T05:05Z. It labels its mode `live` but also states `Live Inference: False` and `Ollama Reachable: False`; OCR is unavailable for all four attempted cases. Its zero OCR metrics are not measured zero error. The report includes small scenario counts for routing, RAG, grounding/citations and deterministic tools; these do not constitute broad live model validation. Its script supports deterministic/mock/live modes, so the report's explicit metadata matters more than the mode label.
- `live_e2e_quantitative.md/json` reports four live OCR fixture cases using `qwen3.5:4b`: 7.91% macro CER and 4.42% micro CER, mean WER 0.3444, mean keyword recall 0.7188. The ambiguous serial case was 24.44% CER. This is genuine live local inference evidence for those fixtures only.
- `final_live_ocr.md/json` reports a later live four-fixture run: 4.71% macro CER, 3.32% micro CER, mean WER 0.3167 and mean keyword recall 0.7188. The ambiguous tag was 13.33% CER, WER 1.0, and zero expected-keyword recall. The per-fixture results and latency are in the report/JSON; live model predictions vary between runs.
- `ocr_preprocessing_small_images.json` is a paired same-fixture/same-GT experiment with `qwen3.5:4b`, temperature 0, 1024 tokens and `think=false`. 2x Lanczos current path: ambiguous tag 6 edits / 45 reference chars = 13.33% CER, WER 1.0, 1,466.61 ms. A single 4x nearest-neighbor trial: 3 substitutions / 45 = 6.67% CER, WER 1.0, 2,540.55 ms. It is one stochastic model run, not a repeated or production-validated improvement. Ground truth was not modified. A PDF keyword annotation mismatch (`TG-UNIT-4` absent from reference transcription) is documented in the OCR audit.
- `held_out_routing_report.md/json` records 35/35 routing examples correct, but measures the configured router on a fixed challenge file; it does not prove broad production intent accuracy or LLM reasoning quality.

Evaluation weaknesses: very small synthetic fixture sets; some evaluation JSON uses unavailable outputs or scripted cases; limited repeats for nondeterministic model behavior; a held-out set may not represent independent operational data; zero/empty metrics can be ambiguous when cases are skipped; keyword annotations need consistency review; no demonstrated inter-annotator ground truth protocol. Credible claims need fixed datasets and hashes, independent held-out cases, versioned settings/model hashes, repeat runs/confidence intervals, clear live-vs-mock reporting, actual retrieval/citation evidence traces, and human-reviewed OCR references.

## 6. Confirmed defects and notable risks

1. **DOCX workflow is incomplete in UI:** latest browser test failed generation and download (2/13). Current source adds shared DOCX argument validation and contract tests, but no later successful full browser DOCX run is in the saved artifacts inspected here.
2. **Citation evidence has conflicting live outcomes:** the earlier API log produced no verified citations despite its success banner; the later API and browser acceptance runs passed; a previous refusal diagnostic reportedly emitted an invented manual citation on empty retrieval. Stronger validator code and tests exist in the dirty tree, but broad live/adversarial proof is still absent.
3. **Model refusal assertion is nondeterministic:** historical repetitions included a failure; a later modified test reportedly passed four serial repeats. The historical response wording was not preserved as a separate log, and the result depends on a local model response.
4. **Sandbox isolation is unverified:** Docker client existed in the earlier diagnostic, but Docker Desktop Linux engine named pipe was absent. No real allowed/denied/filesystem/timeout/resource/cleanup/image-failure runtime tests ran.
5. **Network isolation is not proven:** Compose default network is externally routable (`internal: false`); offline guard is application-level; a prior host HTTPS request returned HTTP 200. Do not advertise an air gap.
6. **OCR identifiers are unsafe for unattended use:** the ambiguous serial fixture still has WER 1.0 even in the best one-run candidate.
7. **Docs contain claims that exceed evidence:** architecture/operations docs use “air-gapped” and “complete air-gap” language, while the implementation notes and tests establish only application-level controls and unverified Docker configuration. Model names and deployment descriptions also differ between README/architecture/operations. Align docs with actual defaults and proven controls before external use.

## 7. Partial and blocked verification

- **Blocked:** live Docker sandbox verification and full Docker Compose deployment due unavailable Docker daemon/engine pipe in the preceding diagnostic.
- **Not established:** host-wide or container egress restriction, firewall enforcement, packet-level verification, clean offline install, or full offline model provisioning.
- **Failed in latest full browser run:** DOCX generation and DOCX download.
- **Not independently reproduced in this audit:** full pytest, Ruff, Mypy, frontend build/lint and air-gap script. Their prior results are described above and were not run again.
- **Not established:** restart/recovery persistence, production Postgres migration and backup/restore, concurrency/load, long-duration operation, full TOTP lifecycle, cancellation/timeout across all service calls, broad malformed upload and hostile-document matrices, and operational monitoring/backup controls.

## 8. Security and confidentiality assessment

- **Authentication/password storage:** password hashing and signed-token auth are implemented; setup is interactive and the project does not define a universal default login password. Saved login flows pass. Production key management, account recovery and lifecycle controls still need site validation.
- **Authorization:** role-aware dependencies/tool gating exist and one admin workflow passed. Verify every endpoint and object ownership boundary before confidential use.
- **Upload/filesystem:** size and workspace/path checks exist; traversal attack was blocked in saved API acceptance. This does not establish resistance to all symlink/race/archive/parser attacks or cross-user access patterns.
- **Prompt injection/citations:** there are tests and current validator hardening, but retrieved documents remain untrusted instructions and live evidence includes a fabricated-source diagnostic. Require adversarial corpus tests, evidence-grounded response policy and human review.
- **Sandbox:** source asks Docker for `network_mode=none`, capability drop, non-root user, memory/CPU/process limits, timeout and cleanup with fail-closed semantics. Runtime behavior is **not verified**. Never treat mocked tests or source configuration as isolation proof.
- **Network:** Python urllib guard is a narrow application-level measure. It does not block raw sockets in other code, subprocess traffic, native clients or unrelated host processes. Local port bindings are not outbound restrictions. External HTTPS reachability was previously demonstrated.
- **Secrets/logging:** configuration rejects some weak placeholders; do not place secrets into reports. A repository hygiene check is reported as passed historically, but local ignored `.env` and logs exist and were not opened in this audit. Confirm log redaction on real requests before deployment.
- **Persistence:** SQLite is used in the synthetic browser environment; PostgreSQL/pgvector is configured for Compose. Production backup/restore and encryption/access controls are not evidenced.

### Readiness by use case

| Use | Decision | Basis |
|---|---|---|
| Academic demonstration with synthetic data | **GO with disclosed limitations** | Browser shows login/upload/RAG/citation navigation/XLSX download; API run reports broader success. Demonstrate DOCX failure as a known limitation, keep a fallback prepared, disclose OCR and network limits. |
| Controlled local synthetic-data testing | **GO with controls** | Use only fixed synthetic fixtures, local model, isolated test DB/workspace and human review. Keep code sandbox unavailable/fail-closed and do not call host setup air-gapped. |
| Real confidential industrial data | **NO-GO** | Host/container egress controls, live sandbox isolation, robust citation/refusal guarantees, operational data protection and OCR identifier reliability are not established. |
| Production deployment | **NO-GO** | Deployment stack not live-verified; network/sandbox/database operations, recovery, load, audit retention, incident controls and security assessment remain incomplete. |

## 9. Quantitative evaluation and OCR assessment

Available suites include unit tests for OCR, parsers, retrieval, routing, identity, tools, sandbox, audit and evaluation metrics; scripted quantitative reports; a 35-case held-out router challenge; a small live OCR suite; and browser/API acceptance scripts. Live local model evidence exists for the selected OCR runs and agent workflows. Other quantitative report portions explicitly have `Live Inference: False`; do not present them as end-to-end live model scores.

The OCR evaluator records exact references/predictions and edit counts; CER is character edit distance divided by reference character count, WER is word edit distance divided by reference word count, and the report aggregates macro (mean per fixture) and micro (total edits / total reference characters). The four fixtures are a clean plate, ambiguous serial tag, pump telemetry table, and scanned turbine inspection PDF. OCR reports give latency per fixture. Metrics should be interpreted as benchmark behavior on synthetic files, not on real plant scans. OCR normalization and keyword recall definitions should be documented alongside any claims.

Retrieval and citation metrics are based on a tiny synthetic corpus/challenge in the current reports; the report labeled live inference false does not prove real model grounding. The browser and API acceptance do demonstrate an actual synthetic query and source in selected runs, but do not establish general retrieval precision or entailment. Routing challenge results mostly demonstrate deterministic router behavior on provided examples rather than open-ended agent correctness. The code supports a mock provider, so each report must identify provider and mode.

## 10. Completion estimates

These are engineering judgments about breadth and evidence, not objective percentages:

| Category | Estimate | Rationale |
|---|---:|---|
| Core functionality | 75–85% | Main UI/API/agent/knowledge/tool paths exist and synthetic acceptance works; DOCX UI flow remains defective. |
| Frontend usability | 70–80% | Core flows and Knowledge Hub are exercised by Chrome; acceptance still has a deliverable failure and broader accessibility/usability evidence is absent. |
| Backend reliability | 60–75% | Broad historical automated coverage and selected live workflows; model-dependent refusal and lifecycle/load/recovery are unresolved. |
| Agent/model integration | 60–75% | Local model tools and RAG execute; refusal and citation behavior can vary; model fallback/latency/stream cancellation not fully validated. |
| RAG/citation quality | 55–70% | Positive controlled examples, but contradictory acceptance and fabricated citation diagnostic limit trust. |
| OCR quality | 45–60% | Four measured fixtures and iterative experiments; ambiguous serial remains unacceptable without human review. |
| Security | 40–55% | Auth/path checks and code controls exist; Docker runtime and network boundary not evidenced; no formal security assessment. |
| Testing/reproducibility | 70–80% | 276-test historical run and saved evaluations; current dirty tree differs, not all logs are raw, benchmark scope is small. |
| Deployment readiness | 35–50% | Compose/docs/config exist but Docker deployment, host isolation, recovery and operational controls are not demonstrated. |
| Documentation/academic presentation | 65–80% | Broad docs and evidence artifacts exist; claims conflict and several quantitative claims require careful qualification. |

**Overall: approximately 65–75%.** The project has broad functional coverage and useful verification work, but it is not end-to-end complete because the latest browser workflow is not all green, sandbox/network guarantees are unproven, and accuracy/reliability evidence is narrow.

## 11. Prioritized roadmap

### Phase A — Before the next academic demonstration

| Priority / task | Why; files | Acceptance criteria | Blockers / effort |
|---|---|---|---|
| P1 — Stabilize DOCX generation from the UI | Latest browser fails DOCX output; inspect `app/tools/doc_gen_validation.py`, `app/tools/registry.py`, `app/agent/graph.py`, prompts and `frontend/src/App.tsx`. | Repeat real-browser run generates a nonempty DOCX, lists it, downloads it through authenticated UI, and parsed content matches requested sections/table. Save result and screenshot. | Local model/runtime; 0.5–1.5 days. |
| P1 — Make citation/refusal behavior demonstrably safe on synthetic adversarial cases | Conflicting logs and source hallucination risk; inspect citation validator/service and refusal integration tests. | Empty retrieval always returns safe abstention; fabricated source/quote never appears in visible answer or clickable links; repeat live model run is captured; passing tests assert invariants rather than exact model phrase. | Model stochasticity; 1–2 days. |
| P2 — Align demo and docs with verified limits | README/docs currently overstate air-gap/security and diverge on model names. | User-facing docs call isolation application-level unless actual OS/container policies are deployed; correct models/setup; demo script includes limitations/fallback. | None; 0.5 day. |

### Phase B — Before claiming end-to-end completion

| Priority / task | Why; files | Acceptance criteria | Blockers / effort |
|---|---|---|---|
| P0 — Verify Docker sandbox on real daemon | `app/sandbox/docker_sandbox.py`, `tests/test_sandbox`, Docker runtime. | On supported daemon, prove allowed/denied execution, workspace boundaries, timeout, memory/CPU/PID limits, forced cleanup, missing daemon/image failure; fail-closed remains intact. Save daemon/image versions and raw results. | Docker Desktop engine was unavailable; 1–3 days after environment provision. |
| P0 — Establish actual network control policy | `docker-compose.yml`, `app/network/offline_guard.py`, OS firewall. | Controlled test demonstrates intended outbound policy at host/container layer; inspect firewall rules and egress paths. Do not call air-gapped unless all relevant egress paths are blocked and independently checked. | Requires approved firewall/container policy; 1–3 days. |
| P1 — Complete end-to-end browser suite | browser acceptance script and frontend. | Browser-driven checks cover login, upload, RAG, citations, Knowledge Hub actions, DOCX/XLSX and both downloads; attach output and screenshots; distinguish API assertions. | DOCX root cause; 0.5–1 day after repair. |
| P1 — Fresh regression on exact final tree | Python tests, Ruff/Mypy, frontend build/lint, air-gap verifier. | Save reproducible command outputs, counts and skip reasons after final edits; full suite passes or failures are triaged. | Local models and Windows symlink privilege; 1–2 hours. |
| P1 — Validate database and user lifecycle | DB/migrations, auth/audit. | Fresh Postgres deployment, migration, restart persistence, backup/restore and permission tests pass with synthetic data. | Docker; 1–2 days. |

### Phase C — Future improvements

| Priority / task | Why; files | Acceptance criteria | Dependencies / effort |
|---|---|---|---|
| P2 — Improve OCR for serials with repeated held-out evaluation | `app/knowledge/ocr/vision_engine.py`, OCR fixtures/evaluator. | Multiple independent runs and additional synthetic/consented fixtures improve both CER and exact identifier accuracy without regressing tables/PDFs; retain human confirmation for critical tags. | More reviewed fixtures; 2–5 days. |
| P2 — Expand citation and prompt-injection evaluation | citation validator, eval corpus and integration tests. | Versioned adversarial cases include hostile documents, retrieved-but-irrelevant sources, source-ID injection and conflicting evidence; publish precision/recall with manually reviewed labels. | Annotation; 3–7 days. |
| P2 — Expand held-out routing/retrieval set | evaluation data and runners. | Separate development/test splits, hashes and distribution coverage; no route examples copied from tuning set. | Dataset curation; 2–5 days. |
| P3 — Operational hardening and UX | monitoring, cancellation, error recovery, accessibility. | Load, soak, cancellation, backup, operator workflow and accessibility checks meet documented requirements. | Deployment target; 1–3 weeks. |

## 12. Academic-demo readiness checklist

- Use only the documented synthetic fixtures and isolated test database/workspace.
- Confirm the local Ollama models and app services are available before presenting.
- Rehearse the browser flow; DOCX is currently not dependable in the latest saved run. Keep the known good separate artifact only as a clearly labeled fallback, not proof of current browser flow.
- Show the source/citation inspector and disclose both the failed historical citation run and later successful runs.
- Do not rely on OCR to decide an ambiguous serial number; verify it manually.
- Describe the network control as application-level; do not call the workstation or Compose stack air-gapped.
- Do not execute untrusted code while Docker runtime isolation is unavailable.
- Avoid real confidential or safety-critical decisions; generated engineering outputs require human review.

## 13. Remaining uncertainties and evidence gaps

- Current dirty source tree differs from the revision at which historical full-suite/lint/type/build results were captured; exact mapping of each check to each current change is not available.
- No durable raw stdout for every historical full suite/lint/type/air-gap check was located; the saved Markdown report records the commands and totals.
- No successful DOCX browser generation-and-download record exists in the latest complete run.
- Docker sandbox runtime and Compose service startup were not verified against a live daemon.
- Host outbound access was previously observed; effective enterprise firewall rules and container egress were not tested. No “air gap” finding is justified.
- Refusal failure response was not separately captured in the earlier report; later repeat passes do not establish deterministic model behavior.
- OCR best serial result is one inference on one synthetic tag, with WER 1.0; no repeatability or field accuracy evidence exists.
- Authorization coverage, upload threat model, TOTP lifecycle, streaming cancellation, Postgres persistence/recovery, performance/load, dependency/model provisioning and operational controls need focused evidence.

## 14. Exact next three actions

1. Reproduce and fix the UI DOCX tool contract on the current branch, then prove a real browser generation **and download** with parsed output.
2. After the final code edit, run and save a fresh full test/build/lint/type verification set on this exact working tree; distinguish skipped platform tests and preserve all existing logs.
3. Enable a supported Docker daemon in a controlled test environment and verify fail-closed sandbox behavior and actual network policy before any claim of confidential-data readiness.

## Audit commands and scope

Read-only commands executed for this status audit included:

```powershell
Get-Location
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git status --ignored --short
git log -5 --oneline --decorate
git remote -v
git rev-list --left-right --count 'HEAD...origin/main'
git diff --stat
git diff --name-status
git ls-files --others --exclude-standard
Get-ChildItem eval\reports -File
Get-ChildItem eval -Recurse -File
rg --files
rg -n -i "TODO|FIXME|XXX|NotImplemented|placeholder|not implemented|mock" app frontend/src scripts eval
```

Selected report/log/source files were read, and the saved browser JSON/OCR JSON was parsed read-only for summaries. No pytest, frontend build/lint, Ruff, Mypy, migration, external network request, Docker command, database mutation, personal-directory scan, source-code edit, stage, commit, reset or push was performed for this audit. The only file created by this task is this requested report.

## Completion repair follow-up — 2026-10-26

This follow-up records work performed after the read-only audit above. It supersedes the earlier status for DOCX browser acceptance and current-tree regression checks only. Older failed and successful logs remain separate and unchanged.

### Changes made

- `app/agent/service.py`, `app/agent/state.py`, and `app/agent/citation_validator.py`: when a model answer fails citation validation but the request retrieved a query-matched RAG sentence, the service can return that exact verbatim excerpt with the retrieved filename, after validating it again. `evidence_fallback_used` is returned, and audit events retain the rejected model-validation flags. It does not use non-RAG tool text or invent source metadata.
- `app/agent/prompts.py`: asks for concise source-close RAG answers and avoids claiming host/deployment air-gap isolation without verified controls.
- `app/tools/doc_gen_validation.py`: Python 3.11-compatible scalar check formatting; existing shared input validation remains in place.
- `tests/test_agent/test_service.py`, `tests/test_citation_validator.py`: tests for exact-evidence fallback, empty/unrelated retrieval refusal, and fabricated citation rejection.
- `tests/test_integration/test_real_agent_workflow.py`: expects the exact synthetic maximum `78.5` (rather than also accepting the unrelated 80 C trip limit) and provides failure diagnostics. `tests/test_integration/test_industrial_workflow_acceptance.py` now checks files under the configured workspace, keeping full-suite runs isolated.
- `eval/post-audit-2026-10-26-completion/browser_acceptance.cjs`: isolated acceptance harness copy uses an explicit XLSX argument example and scopes the download link to the exact artifact row. The prior attempt showed the former selector could select the DOCX link for XLSX.
- Ruff cleanup in the local evaluation/acceptance scripts removes an unused import, sorts imports and marks intentional CLI output. Existing frontend files were not edited in this follow-up.

### Current verification evidence

| Verification | Result and exact command | Evidence/limits |
|---|---|---|
| Full Python suite | **291 passed, 1 skipped, 0 failed** in 84.41 s (292 collected). `.venv\Scripts\python.exe -m pytest -o 'addopts=--tb=short' -q -ra --basetemp=eval\.completion-full-tests-final-2026-10-26` with `OLLAMA_NO_CLOUD=1`, local Ollama and isolated SQLite/workspace environment. | Skip: `tests/test_tools/test_adversarial_security.py:71`, Windows disallows symlink creation. Full suite ran against current code before the final Ruff-only style cleanup; targeted regression was rerun after that cleanup. |
| Targeted regressions | **28 passed.** `.venv\Scripts\python.exe -m pytest tests\test_citation_validator.py tests\test_tools\test_doc_gen_contract.py tests\test_agent\test_service.py -q -ra --basetemp=eval\.completion-core-final-2026-10-26`. | Includes DOCX contract and source-excerpt fallback tests. |
| Live model RAG stability | Four consecutive passes of `tests\test_integration\test_real_agent_workflow.py::test_real_agent_grounded_rag_workflow`, with isolated temporary directories `eval\.completion-rag-fallback-repeat-1` through `-4`, local Ollama and `OLLAMA_NO_CLOUD=1`. | Earlier before fallback, the same live RAG test had intermittent safe-abstention failures when its citation failed lexical validation despite relevant retrieval. A concise prompt alone did not fix it (four failures). The fallback now supplies an exact, query-matched retrieved sentence and revalidates it. This is four repetitions, not a universal reliability guarantee. |
| Real browser acceptance | **13/13 passed** using Chrome + Playwright Core on a clean stack and a fresh synthetic DB. Authoritative run record: `eval/post-audit-2026-10-26-completion/browser_acceptance_verified-final-explicit-docx-2026-10-26.json`; screenshots use `verified-final-explicit-docx-2026-10-26-browser-*.png`. | Browser login, upload, chunk inspection, retrieval, agent citation, citation drawer/navigation, DOCX/XLSX generation, both downloads, and no uncaught page errors passed. Backend startup log confirms the fresh `acceptance-final.sqlite3` database. |
| Downloaded DOCX/XLSX content | DOCX: 36,828 bytes, parsed by `python-docx`, three paragraphs; expected 450 Nm and source filename present. XLSX: 5,131 bytes, parsed by `openpyxl`; sheet `Synthetic Turbine Metrics`, header `(Metric, Value, Source)`, expected synthetic torque/source row. Browser-captured artifact GETs returned HTTP 200. | Files: `eval/post-audit-2026-10-26-completion/downloads/browser_demo_report.docx` and `browser_demo_metrics.xlsx`. |
| Ruff | `.venv\Scripts\ruff.exe check .` — **All checks passed!** | Run after lint cleanup. |
| Mypy | `.venv\Scripts\mypy.exe app` — **no issues in 74 source files**. | Current project code at the time of run. |
| Frontend build/lint | `npm run build` and `npm run lint` from `frontend/` — **both passed**; TypeScript/Vite built 1,938 modules. | Frontend source remained preserved. |
| Application-level verifier | `.venv\Scripts\python.exe scripts\verify_airgap.py` — **6/6 passed**. | Proves only the verifier's application/source/profile checks. Its own output says OS firewall controls are required for full isolation. |
| Diff check | `git diff --check` exited 0; Git emitted line-ending conversion notices only. | No files were staged or committed. |

The sequence includes preserved failed test basetemp outputs and a failed-start log directory at `eval/post-audit-2026-10-26-completion/failed-start-logs/`. They were not folded into the successful browser result. The final successful output has its own JSON, screenshots, downloads and process/log directory.

**Verification provenance correction:** `browser_acceptance_completion-final-2026-10-26.json` was produced before the latest source was loaded and is not authoritative for the current code. It is retained unchanged. After stopping only the earlier project test processes (leaving unrelated Docker Desktop/WSL relay processes untouched), a new backend started on 2026-10-26 at 15:50 local time and logged initialization of `acceptance-final.sqlite3`. The first fresh browser attempt `verified-final-current-code-2026-10-26` returned a valid DOCX under a model-derived filename and failed the expected-filename assertion; the harness was then updated to send an exact DOCX argument object. The subsequent `verified-final-explicit-docx-2026-10-26` run passed 13/13 on that fresh database and current-source backend. Use this latter run as the current browser proof.

### Remaining blockers and updated decisions

`docker context ls`, `docker version`, and `docker info --format '{{.ServerVersion}}'` were checked again on 2026-10-26. The Docker client is 29.7.2, but `desktop-linux` cannot connect to `npipe:////./pipe/dockerDesktopLinuxEngine` because that named pipe does not exist. No live Docker execution, isolation, timeout, resource, cleanup or failure-mode test was possible. The earlier controlled host request to `example.com` returned HTTP 200, Compose still has `internal: false`, and the application verifier remains a software-level check. **Do not describe this system as host-isolated or fully air-gapped.**

**Academic demonstration with synthetic data: GO with disclosed limits.** The latest real browser run now covers both DOCX and XLSX generation and downloads, and the entire current Python suite passed except the Windows symlink skip. Use synthetic data, state the OCR and model variability limits, and keep the Docker sandbox disabled/fail-closed.

**Controlled synthetic-data testing: GO with controls.** Use isolated paths and local models; the citation fallback only returns a matching retrieved excerpt after revalidation. Preserve human review and do not use generated output as operational authority.

**Confidential industrial data and production: NO-GO.** Docker runtime isolation remains unverified, public host egress was previously observed, host/container firewall enforcement is not proven, and OCR serial accuracy, operational recovery and full deployment controls remain unresolved.

### Docker Desktop follow-up — 2026-10-26

The user started Docker Desktop. Using elevated access only to the Docker named pipe, the real runtime harness in `scripts/verify_docker_sandbox_runtime.py` passed **12/12** checks on Engine 29.7.2 with the pre-existing `python:3.11-slim` image. It verified execution, the sole `/workspace` bind, container-level network denial, non-root privilege/file denial, memory/CPU/PID configuration, timeout and timeout cleanup, successful-run cleanup, invalid workspace rejection, simulated daemon ping failure and a loopback-only missing-image failure. JSON evidence: `eval/post-audit-2026-10-26/docker_sandbox_runtime.json`.

The first live run exposed that the sandbox had been running as root. `DockerSandbox` now passes `user="1000:1000"`; a regression assertion was added. The initial root run's `setuid(0)` and `/etc/shadow` access succeeded, while the final non-root run blocked both. The four targeted sandbox tests passed, and Ruff passed on the changed sandbox, test and harness files. Full pytest was not rerun after this narrow fix.

One initial post-fix attempt reused a directory created by the root-container run and could not overwrite its file as UID 1000. The final run used a clean unique synthetic session. Existing workspaces were preserved; review permissions of any legacy sandbox outputs before reuse. No Docker image was pulled or unrelated service/firewall changed.

This verifies the tested sandbox container configuration only. It does not establish host-wide or whole-application egress isolation: the host previously reached public HTTPS and the Compose network remains externally connected. Therefore:

**Academic demo with synthetic data: GO with disclosed limits.** **Controlled synthetic-data testing: GO with controls and workspace-permission review.** **Confidential industrial data/production: NO-GO** pending host/deployment egress enforcement, stronger OCR for critical identifiers, and operational/security validation.

### GitHub publication preflight — 2026-10-26

The full suite was run after the Docker non-root change, but the local Ollama HTTP endpoint was unavailable to the runner. The first completed attempt ended **275 passed, 15 skipped, 2 failed** in 78.73 seconds; both failures were model-dependent flows that could not connect to Ollama. A second attempt with `OLLAMA_NO_CLOUD=1` could enumerate installed models through the Ollama CLI but the Python HTTP connection to `127.0.0.1:11434` was refused; it ended **279 passed, 12 skipped, 1 failed** in 131.40 seconds, failing `test_real_ollama_health_and_list`. Do not present these as green runs. The last complete model-enabled pass remains the earlier recorded 291 passed / 1 skipped / 0 failed, before the final narrow Docker user setting. Since that fix, the four sandbox unit tests and the live 12/12 Docker harness passed. No code was changed to suppress the missing-service results.
