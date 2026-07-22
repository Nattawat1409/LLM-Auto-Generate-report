"""Resolve + stream html/pdf for a session.

Reads state via workflow.get_snapshot() — never imports app.graph directly.
"""
from pathlib import Path

from app.api.services import workflow
from app.api.errors import SessionNotFoundError, ArtifactNotReadyError


async def get_html(thread_id: str) -> str:
    snapshot = await workflow.get_snapshot(thread_id)
    if not snapshot.values:
        raise SessionNotFoundError(thread_id)
    html = snapshot.values.get("html_detail")
    if not html:
        raise ArtifactNotReadyError(thread_id, artifact="html")
    return html


async def get_pdf_path(thread_id: str) -> Path:
    snapshot = await workflow.get_snapshot(thread_id)
    if not snapshot.values:
        raise SessionNotFoundError(thread_id)
    pdf_path = snapshot.values.get("generate_pdf")
    if not pdf_path or not Path(pdf_path).exists():
        raise ArtifactNotReadyError(thread_id, artifact="pdf")
    return Path(pdf_path)
