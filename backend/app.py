"""Safe HTTP adapter for Taiwan legal judgment search.

This service uses the parser/search clients from mcp-taiwan-legal-db, but never
starts its Playwright WAF-bypass fallback. If the upstream rejects an ordinary
request, the caller receives a clear error and can open the official source.
"""

from __future__ import annotations

import os
import re
import ssl
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from mcp_server.cache.db import CacheDB
from mcp_server.tools.judicial_doc import JudgmentDocClient
from mcp_server.tools.judicial_search import JudicialSearchClient
from mcp_server.tools.waf_bypass import JudicialWAFBypass, WAFPermanentBlockError

JID_PATTERN = re.compile(r"^[A-Z]{2,6},\d+,[^,]+,[0-9A-Za-z-]+,\d{8},\d+$")
DEFAULT_ORIGINS = "https://kobejordanair-bit.github.io,http://localhost:5173,http://127.0.0.1:5173,http://localhost:8012,http://127.0.0.1:8012"
_DEFAULT_SSL_CONTEXT_FACTORY = ssl.create_default_context


def official_tls_context(*args: Any, **kwargs: Any) -> ssl.SSLContext:
    """Keep normal TLS validation while tolerating a known official CA extension defect.

    Certificate-chain trust, expiry, and hostname checks remain enabled. Only
    OpenSSL's extra X509 strict-extension flag is cleared because the upstream
    Taiwanese government certificate chain currently lacks a required SKI.
    """
    context = _DEFAULT_SSL_CONTEXT_FACTORY(*args, **kwargs)
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


# The imported client creates httpx clients internally. Apply the narrowly
# documented TLS compatibility context before those clients are constructed.
ssl.create_default_context = official_tls_context


class NoAutomationWAF:
    """Detect WAF blocks but never automate a browser or solve a challenge."""

    def get_cookies(self) -> dict[str, str]:
        return {}

    @staticmethod
    def is_blocked(response_text: str) -> bool:
        return JudicialWAFBypass.is_blocked(response_text)

    async def refresh(self) -> None:
        raise WAFPermanentBlockError(
            "官方網站拒絕自動查詢；本服務不會嘗試繞過防護。"
        )


class JudgmentSearchRequest(BaseModel):
    keyword: str = Field(default="", max_length=100)
    court: str = Field(default="", max_length=40)
    case_type: str = Field(default="", max_length=10)
    year_from: int = Field(default=0, ge=0, le=150)
    year_to: int = Field(default=0, ge=0, le=150)
    case_word: str = Field(default="", max_length=20)
    case_number: str = Field(default="", max_length=30)
    main_text: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def has_a_search_term(self) -> "JudgmentSearchRequest":
        if not any((self.keyword.strip(), self.case_number.strip(), self.main_text.strip())):
            raise ValueError("請至少輸入關鍵字、案號或主文關鍵字")
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("起始年度不得晚於結束年度")
        return self


def _safe_search_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not data.get("success"):
        raise HTTPException(status_code=503, detail=data.get("error", "暫時無法查詢司法院資料"))
    results = data.get("results", [])[:10]
    return {"total_count": min(int(data.get("total_count", len(results))), 10), "results": results}


def _safe_document_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not data.get("success"):
        raise HTTPException(status_code=503, detail=data.get("error", "暫時無法取得裁判書"))
    allowed = (
        "case_id", "court", "date", "cause", "main_text", "facts", "reasoning",
        "full_text", "source_url", "cited_statutes", "cited_cases",
    )
    return {key: data.get(key, "" if key not in {"cited_statutes", "cited_cases"} else []) for key in allowed}


def create_app(search_client: Any | None = None, document_client: Any | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cache: CacheDB | None = None
        try:
            if app.state.search_client is None or app.state.document_client is None:
                cache_path = Path(os.getenv("LEGAL_CACHE_PATH", "/tmp/legal-judgments-cache.db"))
                cache = CacheDB(db_path=cache_path)
                await cache.initialize()
                waf = NoAutomationWAF()
                app.state.search_client = JudicialSearchClient(cache, waf)
                app.state.document_client = JudgmentDocClient(cache, waf)
            yield
        finally:
            client = app.state.document_client
            if isinstance(client, JudgmentDocClient):
                await client.close()
            if cache is not None:
                await cache.close()

    app = FastAPI(title="Taiwan Legal Import API", version="0.1.0", lifespan=lifespan)
    app.state.search_client = search_client
    app.state.document_client = document_client
    origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", DEFAULT_ORIGINS).split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "service": "Taiwan Legal Import API",
            "status": "ok",
            "health": "/health",
            "docs": "/docs",
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "waf_bypass": "disabled"}

    @app.post("/api/judgments/search")
    async def search_judgments(request: JudgmentSearchRequest) -> dict[str, Any]:
        result = await app.state.search_client.search(
            keyword=request.keyword.strip(),
            court=request.court.strip(),
            case_type=request.case_type.strip(),
            year_from=request.year_from,
            year_to=request.year_to,
            case_word=request.case_word.strip(),
            case_number=request.case_number.strip(),
            main_text=request.main_text.strip(),
            max_results=10,
        )
        return _safe_search_payload(result)

    @app.get("/api/judgments/document")
    async def get_judgment_document(
        jid: str = Query(min_length=12, max_length=200),
    ) -> dict[str, Any]:
        if not JID_PATTERN.fullmatch(jid):
            raise HTTPException(status_code=422, detail="裁判書識別碼格式不正確")
        result = await app.state.document_client.get_by_jid(jid)
        return _safe_document_payload(result)

    return app


app = create_app()
