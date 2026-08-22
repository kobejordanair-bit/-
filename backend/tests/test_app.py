from fastapi.testclient import TestClient

import ssl

from app import create_app, official_tls_context


class FakeSearchClient:
    async def search(self, **kwargs):
        assert kwargs["keyword"] == "相當因果關係"
        assert kwargs["max_results"] == 10
        return {
            "success": True,
            "total_count": 1,
            "results": [
                {
                    "jid": "TPSV,112,台上,1,20240101,1",
                    "case_id": "112年度台上字第1號",
                    "court": "最高法院",
                    "case_type": "民事",
                    "date": "112-01-01",
                    "cause": "損害賠償",
                    "summary": "摘要",
                    "url": "https://judgment.judicial.gov.tw/FJUD/data.aspx?ty=JD&id=example",
                }
            ],
        }


class FakeDocumentClient:
    async def get_by_jid(self, jid):
        assert jid == "TPSV,112,台上,1,20240101,1"
        return {
            "success": True,
            "case_id": "112年度台上字第1號",
            "court": "最高法院",
            "date": "112-01-01",
            "cause": "損害賠償",
            "main_text": "主文內容",
            "facts": "事實內容",
            "reasoning": "理由內容",
            "full_text": "完整裁判書內容",
            "source_url": "https://judgment.judicial.gov.tw/FJUD/data.aspx?ty=JD&id=example",
        }


def test_search_returns_a_small_metadata_list():
    app = create_app(search_client=FakeSearchClient(), document_client=FakeDocumentClient())
    client = TestClient(app)

    response = client.post("/api/judgments/search", json={"keyword": "相當因果關係"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert payload["results"][0]["case_id"] == "112年度台上字第1號"
    assert "full_text" not in payload["results"][0]


def test_search_rejects_empty_queries():
    app = create_app(search_client=FakeSearchClient(), document_client=FakeDocumentClient())
    client = TestClient(app)

    response = client.post("/api/judgments/search", json={})

    assert response.status_code == 422


def test_document_returns_importable_sections():
    app = create_app(search_client=FakeSearchClient(), document_client=FakeDocumentClient())
    client = TestClient(app)

    response = client.get("/api/judgments/document", params={"jid": "TPSV,112,台上,1,20240101,1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["main_text"] == "主文內容"
    assert payload["reasoning"] == "理由內容"
    assert payload["source_url"].startswith("https://judgment.judicial.gov.tw/")


def test_document_rejects_malformed_jid_before_fetching():
    app = create_app(search_client=FakeSearchClient(), document_client=FakeDocumentClient())
    client = TestClient(app)

    response = client.get("/api/judgments/document", params={"jid": "not-a-jid"})

    assert response.status_code == 422


def test_official_tls_context_keeps_certificate_validation_enabled():
    context = official_tls_context()

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
