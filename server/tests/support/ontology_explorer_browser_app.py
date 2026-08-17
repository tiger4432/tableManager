"""Isolated browser-QA app for the file-backed Ontology Explorer sample."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from admin_auth import require_admin_token, require_admin_token_strict
from ledger.config_explorer_service import OntologyExplorerService
import ontology_config_explorer_router as explorer_router

from .ontology_explorer_sample import SAMPLE_ROOT, load_transfer_sample_setup


WORKSPACE = Path(__file__).parents[3]
service = OntologyExplorerService(
    config_root=SAMPLE_ROOT,
    draft_root=WORKSPACE / ".test_tmp" / "ontology_explorer_browser_drafts",
    setup_loader=load_transfer_sample_setup,
)
explorer_router.configure_service(service)

app = FastAPI()
app.dependency_overrides[require_admin_token] = lambda: None
app.dependency_overrides[require_admin_token_strict] = lambda: None
app.include_router(explorer_router.router)
app.mount("/", StaticFiles(directory=WORKSPACE / "client2" / "dist", html=True), name="client")
