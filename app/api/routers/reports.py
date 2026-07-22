from fastapi import APIRouter, Depends
from fastapi.responses import Response, FileResponse

from app.api.deps import get_session_service, get_workflow_service, get_artifacts_service
from app.api.errors import InvalidTransitionError
from app.api.schemas.common import SessionStatus
from app.api.schemas.reports import (
    StartReportRequest,
    ReviewRequest,
    PersonalizeRequest,
    SessionView,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=SessionView)
async def start_report(body: StartReportRequest, workflow_svc=Depends(get_workflow_service)):
    return await workflow_svc.start_report(body.question)


@router.get("/{report_id}", response_model=SessionView)
async def get_report(report_id: str, session_svc=Depends(get_session_service)):
    return await session_svc.get_session_view(report_id)


@router.post("/{report_id}/review", response_model=SessionView)
async def review_report(
    report_id: str,
    body: ReviewRequest,
    session_svc=Depends(get_session_service),
    workflow_svc=Depends(get_workflow_service),
):
    current = await session_svc.get_session_view(report_id)
    if current.status != SessionStatus.AWAITING_REVIEW:
        raise InvalidTransitionError(report_id, SessionStatus.AWAITING_REVIEW, current.status)

    resume_payload = {
        "action": body.action,
        "report_type": body.report_type or "",
        "notes": body.notes,
        "feedback": body.feedback,
    }
    return await workflow_svc.resume(report_id, resume_payload)


@router.post("/{report_id}/personalize", response_model=SessionView)
async def personalize_report(
    report_id: str,
    body: PersonalizeRequest,
    session_svc=Depends(get_session_service),
    workflow_svc=Depends(get_workflow_service),
):
    current = await session_svc.get_session_view(report_id)
    if current.status != SessionStatus.AWAITING_PERSONALIZE:
        raise InvalidTransitionError(report_id, SessionStatus.AWAITING_PERSONALIZE, current.status)

    resume_payload = {"choice": body.choice, "feedback": body.feedback}
    return await workflow_svc.resume(report_id, resume_payload)


@router.get("/{report_id}/preview")
async def preview_report(report_id: str, artifacts_svc=Depends(get_artifacts_service)):
    html = await artifacts_svc.get_html(report_id)
    return Response(content=html, media_type="text/html")


@router.get("/{report_id}/pdf")
async def download_pdf(report_id: str, artifacts_svc=Depends(get_artifacts_service)):
    pdf_path = await artifacts_svc.get_pdf_path(report_id)
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)
