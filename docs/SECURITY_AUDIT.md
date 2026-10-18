# Security Audit & Vulnerability Remediation Report

## 1. Executive Summary & Security Baseline

This report documents the security posture, threat model, and vulnerability remediation matrix for the **Sovereign On-Premise Agentic AI Workbench**. The system was engineered from the ground up to support confidential, classified, and proprietary industrial workflows (SIH Problem Statement 26117), mandating strict **zero-cloud egress**, robust RBAC, tamper-evident audit trails, and isolated sandbox execution.

The codebase underwent a comprehensive security review against the audited reference repository (`sathwik-anumandla/sovereign-agent`). All critical architectural vulnerabilities identified in the audit have been systematically resolved and verified by automated regression tests and static analysis.

---

## 2. Vulnerability Remediation Matrix

| Vulnerability ID | Finding in Reference Architecture | Severity | Sovereign Workbench Remediation | Status |
|---|---|---|---|---|
| **VULN-01** | **Hardcoded Weak Secrets & Insecure Defaults:** Insecure placeholder secrets (`admin123`, `sovereign_agent_air_gapped_jwt_secret_key_2026`) permitted system startup without warnings. | **Critical** | Pydantic `Settings` model refuses to start if `JWT_SECRET_KEY` is $<32$ characters or matches known placeholder strings. `POSTGRES_PASSWORD` is strictly mandatory. | **RESOLVED** |
| **VULN-02** | **Host Subprocess Fallback in Sandbox:** If Docker was unavailable, code sandbox fell back to running uncontained `subprocess.run([sys.executable, ...])` directly on host OS. | **Critical** | Implemented a strict **fail-closed** policy (`DockerCodeSandbox`). If Docker is offline or unprivileged execution is refused, the tool returns `ToolStatus.BLOCKED` or `FAILED`. Zero host subprocess execution. | **RESOLVED** |
| **VULN-03** | **Unsafe Pickle Deserialization (RCE Risk):** Classifier models were loaded from `.pkl` binary files using `pickle.load()`, introducing arbitrary remote code execution risks if models were tampered with. | **Critical** | Eliminated binary serialization entirely. 3-stage waterfall router fits an in-memory Scikit-learn TF-IDF + Logistic Regression model at server startup in ~15ms. **Zero `.pkl` files on disk.** | **RESOLVED** |
| **VULN-04** | **Unrestricted Outbound Network Egress:** Outbound telemetry and API calls were possible if models hallucinated external endpoints or dependencies. | **High** | Implemented `OfflineGuard` (urllib opener interceptor) blocking all non-loopback connections at the Python runtime level with `OfflineViolationError`. Docker sandbox enforces `network_mode="none"`. | **RESOLVED** |
| **VULN-05** | **Arbitrary Python `eval()` in Math Tools:** Math utilities utilized Python's native `eval()` or unconstrained evaluation, creating expression injection vulnerabilities. | **High** | Replaced with `SymPyASTEvaluator`. Mathematical formulas, derivatives, integrals, and equations are parsed and solved exclusively using SymPy abstract syntax trees without invoking `eval()`. | **RESOLVED** |
| **VULN-06** | **JWT Leakage via Query Parameters:** WebSocket and API authentication accepted JWT bearer tokens in URL query strings (`?token=...`), risking exposure in web server access logs. | **Medium** | Query parameter authentication rejected. All API endpoints and SSE streams mandate standard HTTP `Authorization: Bearer <token>` headers. | **RESOLVED** |
| **VULN-07** | **Path Traversal in Artifact & Workspace File IO:** Relative file paths (e.g. `../../etc/passwd` or null-byte injections) could escape session folders. | **High** | Enforced `validate_workspace_path()` on all file reads, writes, artifact downloads, and uploads, strictly ensuring canonical path resolution within approved session boundaries. | **RESOLVED** |
| **VULN-08** | **Unbounded Agent Execution Loops:** Agent orchestrator lacked hard iteration boundaries, risking denial of service and infinite recursive loops on ambiguous prompts. | **Medium** | Built on LangGraph `StateGraph` with a strict `max_iterations = 8` (hard ceiling 15) boundary. State machine transitions directly to `synthesize_node` when limit is hit. | **RESOLVED** |
| **VULN-09** | **Lack of Upload Deduplication & Resource Exhaustion:** Duplicate document uploads could flood pgvector tables and exhaust host memory. | **Medium** | Knowledge ingestion calculates SHA-256 content hashes, verifying uniqueness prior to chunking and vector embedding generation. | **RESOLVED** |
| **VULN-10** | **Docker Containers Open to Public Interfaces:** Docker Compose bound service ports to `0.0.0.0`, exposing Postgres and Ollama to the local LAN. | **High** | All service ports in `docker-compose.yml` (`5432`, `8000`, `11434`, `3000`) are explicitly bound to loopback `127.0.0.1`. | **RESOLVED** |

---

## 3. STRIDE Threat Model & Defense-in-Depth

### 3.1. Spoofing
- **Threat:** Malicious actor attempts to forge JWT identity or bypass MFA.
- **Countermeasure:** Constant-time password verification with dummy hash against unknown usernames to thwart user enumeration timing attacks. RFC 6238 TOTP requires 6-digit dynamic codes with 30-second windows. Tokens signed with HMAC-SHA256 requiring 256-bit entropy keys.

### 3.2. Tampering
- **Threat:** Modification of persistent audit records or session artifacts.
- **Countermeasure:** `audit_events` table is append-only with structured JSON payload, actor IP, session ID, and timestamp. Workspace IO validates realpath containment.

### 3.3. Repudiation
- **Threat:** User denies executing privileged actions (e.g. code sandbox execution, document deletion).
- **Countermeasure:** Every tool dispatch, login attempt, document upload, and artifact generation emits an asynchronous `AuditEvent` capturing actor ID, client IP, action type, and status.

### 3.4. Information Disclosure
- **Threat:** Confidential industrial blueprints leaking via model hallucination or error traces.
- **Countermeasure:** Strict offline network guard actively intercepts non-loopback sockets. Response sanitization separates internal `<think>` reasoning tokens from synthesized responses. Security headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Content-Security-Policy`) prevent clickjacking and MIME confusion.

### 3.5. Denial of Service (DoS)
- **Threat:** User executes resource-intensive loops in Python sandbox or unbounded agent recursions.
- **Countermeasure:** Container sandboxes enforce `pids_limit: 50`, `mem_limit: 512m`, and `timeout: 15s`. Agent loops enforce `max_iterations = 8`. Document uploads are capped at 50 MB (`MAX_UPLOAD_SIZE_BYTES`).

### 3.6. Elevation of Privilege
- **Threat:** Low-privilege viewer executes arbitrary code via tool execution.
- **Countermeasure:** Fine-grained Role-Based Access Control (`require_role()`). Tool registry enforces role gating across both HTTP API and interactive CLI.

#### Tool RBAC Permission Matrix

| Tool Name | Description | Allowed Roles | Policy Enforcement |
|---|---|---|---|
| `math_eval` | Symbolic math & equation solver | `admin`, `developer`, `analyst`, `operator`, `viewer` | Safe SymPy AST parsing, zero `eval()` |
| `rag_search` | Private vector knowledge search | `admin`, `developer`, `analyst`, `operator`, `viewer` | pgvector cosine similarity, collection scoped |
| `spreadsheet` | Tabular data inspection & compute | `admin`, `developer`, `analyst`, `operator`, `viewer` | AST formula whitelist, power $\le 4$, formula sanitization |
| `file_io` | Scoped workspace file read/write/list | `admin`, `developer`, `analyst`, `operator` | Workspace canonical realpath check, atomic writes |
| `doc_gen` | Word, Excel, Markdown generation | `admin`, `developer`, `analyst`, `operator` | Canonical workspace path, format validation |
| `code_sandbox` | Air-gapped Python execution | `admin`, `developer`, `analyst` | Docker `network=none`, `cap_drop=ALL`, fail-closed |

### 3.7. Workspace File Lifecycle & Audit Retention
- **Workspace Isolation:** Every session operates in an isolated folder (`workspace/<session_id>/`). Path traversal, symlink escapes, and Windows junction escapes are actively blocked by canonical realpath verification.
- **Quarantined CLI Staging:** External files attached via the CLI are staged into `workspace/<session_id>/uploads/`, preventing the agent from browsing the host filesystem.
- **Upload Protection:** Files inside `uploads/` are immutable and protected against modification or deletion by `file_io`.
- **Decoupled Audit Retention:** Workspace scratch files can be purged (`file_io cleanup`) without impacting persistent, tamper-evident audit logs in the PostgreSQL `audit_events` table.

---

## 4. Verification Evidence & Automated Auditing

The platform includes two continuous security testing suites:
1. **Air-Gap Verification CLI (`python scripts/verify_airgap.py`):**
   - Directly executes active socket egress tests.
   - Inspects application AST for unwhitelisted URL schemas and unsafe serialization functions.
   - Validates Docker Compose network isolation and Git repository cleanliness.
2. **Adversarial Evaluation Benchmark (`tests/test_eval/`):**
   - 15 synthetic industrial benchmark test cases, including prompt injections, jailbreak attempts, path traversal vectors, and sandbox escape simulations.
   - 100% security invariance score across all benchmark evaluations.

```bash
# Security verification execution:
python scripts/verify_airgap.py
pytest tests/test_network/ tests/test_sandbox/ tests/test_identity/
```

---

## 5. Residual Risks & Recommended Production Hardening

While the application layer provides comprehensive controls, production deployment in air-gapped facilities should implement the following host-level measures:
1. **OS Firewall Rules:** Configure host iptables / Windows Defender Firewall to block all outbound TCP/UDP traffic on the physical NIC.
2. **Docker Socket Hardening:** Restrict Docker daemon access strictly to the local `sovereign` user group; never expose the Docker daemon over TCP (`2375`).
3. **Hardware Storage Encryption:** Store PostgreSQL data volumes and workspace directories on BitLocker (Windows) or LUKS (Linux) encrypted volumes with TPM 2.0 key sealing.
