"""DI providers — thin indirection so routers depend on Depends(...) seams
instead of importing service modules directly (eases test overrides)."""
from app.api.services import session, workflow, artifacts


def get_session_service():
    return session


def get_workflow_service():
    return workflow


def get_artifacts_service():
    return artifacts
