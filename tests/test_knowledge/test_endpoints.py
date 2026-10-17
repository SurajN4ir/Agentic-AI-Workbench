"""
tests/test_knowledge/test_endpoints.py
======================================
Integration tests for Knowledge Base and RAG API endpoints.
"""

import pytest
from app.identity.models import User
from app.knowledge.service import get_knowledge_service
from httpx import AsyncClient

from tests.conftest import auth_headers
from tests.test_knowledge.test_service_and_retrieval import MockEmbeddingProvider


class TestKnowledgeEndpoints:
    @pytest.fixture(autouse=True)
    def override_knowledge_service_provider(self) -> None:
        """Injects deterministic mock embedding provider into singleton knowledge service."""
        service = get_knowledge_service()
        service.provider = MockEmbeddingProvider()  # type: ignore[assignment]

    @pytest.mark.asyncio
    async def test_upload_search_list_and_delete_lifecycle(
        self,
        client: AsyncClient,
        test_user: User,
    ) -> None:
        """Complete lifecycle: upload document -> search -> list -> delete."""
        headers = auth_headers(test_user)

        # 1. Upload Document
        file_payload = {
            "file": ("spec.txt", b"Turbine bearing temperature must not exceed 95 degrees Celsius.", "text/plain"),
        }
        data_payload = {"collection_id": "turbine_manuals"}

        r_upload = await client.post(
            "/api/v1/knowledge/upload",
            files=file_payload,
            data=data_payload,
            headers=headers,
        )
        assert r_upload.status_code == 200
        upload_data = r_upload.json()
        assert upload_data["filename"] == "spec.txt"
        assert upload_data["collection_id"] == "turbine_manuals"
        assert upload_data["total_chunks"] >= 1
        doc_id = upload_data["id"]

        # 2. Search Knowledge Base
        search_payload = {
            "query": "maximum turbine bearing temperature limit",
            "collection_id": "turbine_manuals",
            "top_k": 3,
            "min_similarity": 0.0,
        }
        r_search = await client.post(
            "/api/v1/knowledge/search",
            json=search_payload,
            headers=headers,
        )
        assert r_search.status_code == 200
        search_data = r_search.json()
        assert search_data["results_count"] >= 1
        assert "spec.txt" in search_data["formatted_context"]

        # 3. List Documents
        r_list = await client.get("/api/v1/knowledge/documents", headers=headers)
        assert r_list.status_code == 200
        docs = r_list.json()
        doc_ids = [d["id"] for d in docs]
        assert doc_id in doc_ids

        # 4. Delete Document
        r_del = await client.delete(f"/api/v1/knowledge/documents/{doc_id}", headers=headers)
        assert r_del.status_code == 204

        # 5. Verify Document is gone
        r_list_after = await client.get("/api/v1/knowledge/documents", headers=headers)
        docs_after = r_list_after.json()
        doc_ids_after = [d["id"] for d in docs_after]
        assert doc_id not in doc_ids_after

    @pytest.mark.asyncio
    async def test_unauthenticated_request_rejected(self, client: AsyncClient) -> None:
        """Unauthenticated requests receive 401 or 403."""
        r = await client.get("/api/v1/knowledge/documents")
        assert r.status_code in (401, 403)
