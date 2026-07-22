from typing import Literal, Optional

from pydantic import BaseModel

from app.api.schemas.common import SessionStatus

ReportType = Literal["generic", "sales", "customer", "collection_payment"]


class StartReportRequest(BaseModel):
    question: str


class ReviewRequest(BaseModel):
    """Resume dict for human_in_the_loop — field names match what the node reads."""
    action: Literal["approve", "requery"]
    report_type: Optional[ReportType] = None
    notes: str = ""
    feedback: str = ""


class PersonalizeRequest(BaseModel):
    """Resume dict for personalize — field names match what the node reads.

    choice: "1"/"2"/"3" pick an AI-proposed option, "4" is free text (feedback
    required), "5" accepts the report as-is.
    """
    choice: Literal["1", "2", "3", "4", "5"]
    feedback: str = ""


class SessionView(BaseModel):
    session_id: str
    status: SessionStatus
    step: str
    payload: Optional[dict] = None

    @classmethod
    def from_state(
        cls, session_id: str, values: dict, interrupt_value: Optional[dict]
    ) -> "SessionView":
        if interrupt_value is not None:
            if "sql" in interrupt_value:  # human_in_the_loop interrupt shape
                return cls(
                    session_id=session_id,
                    status=SessionStatus.AWAITING_REVIEW,
                    step="human_in_the_loop",
                    payload=interrupt_value,
                )
            # personalize interrupt shape (has "options")
            return cls(
                session_id=session_id,
                status=SessionStatus.AWAITING_PERSONALIZE,
                step="personalize",
                payload=interrupt_value,
            )

        if values.get("is_question_relate") is False:
            return cls(session_id=session_id, status=SessionStatus.REJECTED, step="end")

        return cls(session_id=session_id, status=SessionStatus.DONE, step="end")
