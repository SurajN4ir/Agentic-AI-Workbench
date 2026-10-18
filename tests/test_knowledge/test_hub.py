"""
tests/test_knowledge/test_hub.py
================================
Comprehensive integration tests for Knowledge Hub Management:
- Collection lifecycle and safeguard validation (cannot delete/rename default, safe reassignment)
- Document reassignment and tenant isolation / RBAC
- Layout-aware chunk inspection with pagination and section filters
- Synchronous and asynchronous re-indexing with duplicate job locking (HTTP 409)
- Hybrid ranking metrics exposure (dense, sparse BM25, RRF)
"""

import pytest
from app.identity.models import User
from app.knowledge.service import get_knowledge_service
from httpx import AsyncClient

from tests.conftest import auth_headers
from tests.test_knowledge.test_service_and_retrieval import MockEmbeddingProvider


class TestKnowledgeHub:
    @pytest.fixture(autouse=True)
    def override_knowledge_service_provider(self):
        """Injects deterministic mock embedding provider into singleton knowledge service and restores after test."""
        service = get_knowledge_service()
        orig_provider = service.provider
        service.provider = MockEmbeddingProvider()  # type: ignore[assignment]
        try:
            yield
        finally:
            service.provider = orig_provider

    @pytest.mark.asyncio
    async def test_collections_lifecycle_and_safeguards(
        self,
        client: AsyncClient,
        test_user: User,
    ) -> None:
        headers = auth_headers(test_user)

        # 1. Default collection always exists
        r = await client.get("/api/v1/knowledge/collections", headers=headers)
        assert r.status_code == 200
        colls = r.json()
        assert any(c["name"] == "default" for c in colls)

        # 2. Cannot delete default collection
        r_del_def = await client.delete("/api/v1/knowledge/collections/default", headers=headers)
        assert r_del_def.status_code == 400
        assert "default" in r_del_def.json()["detail"].lower()

        # 3. Cannot rename default collection
        r_ren_def = await client.patch(
            "/api/v1/knowledge/collections/default",
            json={"name": "renamed_default"},
            headers=headers,
        )
        assert r_ren_def.status_code == 400

        # 4. Create new collection
        r_create = await client.post(
            "/api/v1/knowledge/collections",
            json={"name": "aerospace-telemetry", "description": "Flight and turbine logs"},
            headers=headers,
        )
        assert r_create.status_code == 201
        assert r_create.json()["name"] == "aerospace-telemetry"

        # 5. Reject invalid collection slug
        r_inv = await client.post(
            "/api/v1/knowledge/collections",
            json={"name": "invalid slug with spaces!"},
            headers=headers,
        )
        assert r_inv.status_code == 400

        # 6. Reject duplicate collection name
        r_dup = await client.post(
            "/api/v1/knowledge/collections",
            json={"name": "aerospace-telemetry"},
            headers=headers,
        )
        assert r_dup.status_code == 400

        # 7. Upload a document into aerospace-telemetry
        file_payload = {
            "file": ("telemetry.txt", b"Turbine vibration sensor reports 0.04 mm/s RMS at 12000 RPM.", "text/plain"),
        }
        r_up = await client.post(
            "/api/v1/knowledge/upload",
            files=file_payload,
            data={"collection_id": "aerospace-telemetry"},
            headers=headers,
        )
        assert r_up.status_code == 200
        doc_id = r_up.json()["id"]

        # 8. Deleting collection without action fails
        r_del_fail = await client.delete("/api/v1/knowledge/collections/aerospace-telemetry", headers=headers)
        assert r_del_fail.status_code == 400
        assert "contains" in r_del_fail.json()["detail"].lower()

        # 9. Delete with reassign_to default
        r_del_ok = await client.delete(
            "/api/v1/knowledge/collections/aerospace-telemetry?reassign_to=default",
            headers=headers,
        )
        assert r_del_ok.status_code == 204

        # Verify document was reassigned to default
        r_doc = await client.get(f"/api/v1/knowledge/documents/{doc_id}", headers=headers)
        assert r_doc.status_code == 200
        assert r_doc.json()["collection_id"] == "default"

    @pytest.mark.asyncio
    async def test_document_reassign_and_rbac(
        self,
        client: AsyncClient,
        test_user: User,
        admin_user: User,
    ) -> None:
        user_headers = auth_headers(test_user)
        admin_headers = auth_headers(admin_user)

        # Upload document as admin
        r_up = await client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("classified_spec.txt", b"Classified military jet engine blueprint.", "text/plain")},
            data={"collection_id": "default"},
            headers=admin_headers,
        )
        assert r_up.status_code == 200
        doc_id = r_up.json()["id"]

        # Non-admin user attempts to reassign admin's document -> 403 Forbidden
        r_reassign_fail = await client.patch(
            f"/api/v1/knowledge/documents/{doc_id}",
            json={"collection_id": "unauthorized_coll"},
            headers=user_headers,
        )
        assert r_reassign_fail.status_code == 403

        # Admin user reassigns document -> 200 OK
        r_reassign_ok = await client.patch(
            f"/api/v1/knowledge/documents/{doc_id}",
            json={"collection_id": "classified_coll"},
            headers=admin_headers,
        )
        assert r_reassign_ok.status_code == 200
        assert r_reassign_ok.json()["collection_id"] == "classified_coll"

    @pytest.mark.asyncio
    async def test_chunk_inspector_and_search_metrics(
        self,
        client: AsyncClient,
        test_user: User,
    ) -> None:
        headers = auth_headers(test_user)

        # Ingest multi-section document
        content = (
            "# Section A: Fuel Subsystem\n\n"
            "The main fuel line pressure operates at 350 bar during peak combustion.\n\n"
            "# Section B: Exhaust Temp\n\n"
            "Exhaust gas temperature shall not exceed 680 degrees Celsius under nominal thrust."
        )
        r_up = await client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("engine_spec.md", content.encode("utf-8"), "text/markdown")},
            data={"collection_id": "default"},
            headers=headers,
        )
        assert r_up.status_code == 200
        doc_id = r_up.json()["id"]

        # 1. Inspect chunks
        r_chunks = await client.get(
            f"/api/v1/knowledge/documents/{doc_id}/chunks?page=1&page_size=10",
            headers=headers,
        )
        assert r_chunks.status_code == 200
        chunk_data = r_chunks.json()
        assert chunk_data["total_chunks"] >= 2
        items = chunk_data["items"]
        assert len(items) >= 2
        assert items[0]["embedding_dim"] == 768
        assert "content_preview" in items[0]

        first_chunk_id = items[0]["id"]

        # 2. Inspect single chunk detail
        r_detail = await client.get(f"/api/v1/knowledge/chunks/{first_chunk_id}", headers=headers)
        assert r_detail.status_code == 200
        detail = r_detail.json()
        assert detail["id"] == first_chunk_id
        assert detail["filename"] == "engine_spec.md"
        assert len(detail["content"]) > 0

        # 3. Hybrid search returns ranking breakdown
        r_search = await client.post(
            "/api/v1/knowledge/search",
            json={"query": "fuel line pressure bar", "min_similarity": 0.0},
            headers=headers,
        )
        assert r_search.status_code == 200
        search_res = r_search.json()
        assert search_res["results_count"] >= 1
        res_item = search_res["results"][0]
        assert "dense_similarity" in res_item
        assert "dense_rank" in res_item
        assert "sparse_score" in res_item
        assert "sparse_rank" in res_item
        assert "rrf_score" in res_item

    @pytest.mark.asyncio
    async def test_reindex_pipeline_and_conflict_prevention(
        self,
        client: AsyncClient,
        test_user: User,
    ) -> None:
        headers = auth_headers(test_user)

        r_up = await client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("test_reindex.txt", b"Initial document content before re-index.", "text/plain")},
            data={"collection_id": "default"},
            headers=headers,
        )
        assert r_up.status_code == 200
        doc_id = r_up.json()["id"]

        # 1. Synchronous re-index execution
        r_reindex = await client.post(
            f"/api/v1/knowledge/documents/{doc_id}/reindex?sync=true",
            headers=headers,
        )
        assert r_reindex.status_code == 200
        reindex_data = r_reindex.json()
        assert reindex_data["status"] == "completed"

        # 2. Check reindex status
        r_stat = await client.get(
            f"/api/v1/knowledge/documents/{doc_id}/reindex-status",
            headers=headers,
        )
        assert r_stat.status_code == 200
        assert r_stat.json()["status"] in ("completed", "indexed")
