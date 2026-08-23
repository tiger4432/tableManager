"""Isolated browser-QA app for draft lifecycle against the active V2 setup."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from admin_auth import require_admin_token, require_admin_token_strict
from ledger.config_explorer_service import OntologyExplorerService
from ledger.setup import DEFAULT_ONTOLOGY_ROOT
from ledger_api import ontology_config_explorer_router as explorer_router


WORKSPACE = Path(__file__).parents[3]
service = OntologyExplorerService(
    config_root=DEFAULT_ONTOLOGY_ROOT,
    draft_root=WORKSPACE / ".test_tmp" / "ontology_explorer_active_browser_drafts",
)
explorer_router.configure_service(service)

app = FastAPI()
app.dependency_overrides[require_admin_token] = lambda: None
app.dependency_overrides[require_admin_token_strict] = lambda: None
app.include_router(explorer_router.router)
app.mount("/", StaticFiles(directory=WORKSPACE / "client2" / "dist", html=True), name="client")
