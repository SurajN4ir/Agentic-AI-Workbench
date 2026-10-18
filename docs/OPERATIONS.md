# Sovereign Workbench Operations & Deployment Runbook

## 1. System Requirements & Hardware Sizing

### Minimum Host Specifications
- **Operating System:** Windows 11 64-bit, Ubuntu 22.04/24.04 LTS, or RHEL 9.
- **CPU:** 8 cores / 16 threads (e.g. AMD Ryzen 7 / Intel Core i7).
- **RAM:** 24 GB Unified / System Memory.
- **Graphics:** AMD Radeon 860M / Integrated RDNA 3.5 or dedicated GPU with $\ge 4$ GB VRAM.
- **Storage:** 50 GB free NVMe SSD storage (for Docker images, Ollama weights, and pgvector embeddings).

---

## 2. Prerequisites Installation

1. **Docker Engine & Docker Compose:**
   - Install Docker Desktop (Windows) with WSL2 backend, or Docker Engine (Linux).
   - Ensure Docker service is running: `docker info`.
2. **Ollama Local Inference Daemon:**
   - Download and install Ollama from local installation binary or container.
   - Verify Ollama is listening on localhost:
     ```bash
     curl http://127.0.0.1:11434/api/tags
     ```
3. **Download Required Local Model Weights:**
   Run the following commands in an environment with authorized model access prior to physical air-gapping:
   ```bash
   ollama pull qwen2.5:3b
   ollama pull qwen2.5-coder:3b
   ollama pull nomic-embed-text
   # Optional Multimodal Vision Model:
   ollama pull qwen2.5-vl:3b
   ```

---

## 3. Environment Configuration

Copy `.env.example` to `.env` and populate strong, unique production credentials:

```bash
cp .env.example .env
```

### Critical Environment Variables

| Variable | Description | Requirement | Example / Default |
|---|---|---|---|
| `POSTGRES_PASSWORD` | Master password for PostgreSQL database | **Mandatory** | `Sup3rSecur3_Pg_Passw0rd_2026!` |
| `JWT_SECRET_KEY` | Cryptographic key for signing HS256 tokens | **Mandatory** ($\ge 32$ chars) | `openssl rand -hex 32` |
| `STRICT_OFFLINE` | Enables application-level network egress blocking | Recommended | `true` |
| `POSTGRES_HOST` | Database hostname or container service name | Default | `postgres` (or `127.0.0.1` locally) |
| `OLLAMA_BASE_URL` | Loopback address of local Ollama server | Default | `http://ollama:11434` (or `http://127.0.0.1:11434`) |
| `MAX_UPLOAD_SIZE_BYTES` | Maximum allowed document upload size | Default | `52428800` (50 MB) |

> [!WARNING]
> The backend will deliberately **refuse to start** if `JWT_SECRET_KEY` is shorter than 32 characters or contains default strings like `"CHANGE_ME"`.

---

## 4. Production Deployment via Docker Compose

To launch the complete Sovereign Workbench stack (PostgreSQL + pgvector, Backend Monolith, Frontend Nginx):

```bash
docker compose up -d --build
```

### Verifying Service Health
Inspect the container health state:
```bash
docker compose ps
```
All services (`sovereign_postgres`, `sovereign_backend`, `sovereign_frontend`) should report `healthy` or `running`.

Check real-time application logs:
```bash
docker compose logs -f backend
```

---

## 5. First-Time Initialization & Administration

### 5.1. Provision the Initial System Administrator
Execute the secure admin provisioning CLI script:
```bash
# In local Python environment:
python scripts/setup_admin.py --username admin --email admin@sovereign.local --role admin

# Inside Docker backend container:
docker compose exec backend python scripts/setup_admin.py --username admin --email admin@sovereign.local --role admin
```
The script will prompt for a secure password (minimum 12 characters, requiring uppercase, lowercase, numbers, and symbols) and print a base32 TOTP pairing secret along with an ASCII terminal QR code.

### 5.2. Run Database Migrations Manually (if needed)
```bash
docker compose exec backend alembic upgrade head
```

---

## 6. Security & Air-Gap Verification

Execute the automated Sovereign Air-Gap verification script to validate that zero network egress or credential vulnerabilities exist:

```bash
python scripts/verify_airgap.py
```
Expected output:
```
[PASS] Egress Interception Guard
[PASS] Codebase Outbound URL Audit
[PASS] Sandbox Security Profile
[PASS] Secrets & Git Hygiene
[PASS] Docker Compose Profile
[PASS] Serialization & AST Safety
Summary: 6/6 Security & Air-Gap Checks Passed.
```

---

## 7. Running the Industrial Evaluation Benchmarks

Evaluate the workbench across all 15 real-world industrial scenarios:
```bash
python scripts/run_eval.py
```

To run a specific evaluation category:
```bash
python scripts/run_eval.py --category engineering_reasoning
python scripts/run_eval.py --category security_adversarial
```

---

## 8. Backup and Disaster Recovery

### Database Backup (pgvector & Knowledge Base)
```bash
docker compose exec -t postgres pg_dump -U sovereign -d sovereign_workbench -Fc > backup_sovereign_$(date +%Y%m%d).dump
```

### Database Restore
```bash
cat backup_sovereign_YYYYMMDD.dump | docker compose exec -T postgres pg_restore -U sovereign -d sovereign_workbench --clean --if-exists
```

### Persistent Artifacts & Uploads
All uploaded documents and generated artifacts reside in Docker volumes:
- `backend_uploads` -> `/app/uploads`
- `backend_artifacts` -> `/app/artifacts`
- `backend_workspace` -> `/app/workspace`

To archive persistent volumes:
```bash
docker run --rm -v sovereign_backend_artifacts:/data -v $(pwd):/backup alpine tar czf /backup/artifacts_backup.tar.gz /data
```
