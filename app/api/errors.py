from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str):
        self.session_id = session_id


class InvalidTransitionError(Exception):
    def __init__(self, session_id: str, expected: str, actual: str):
        self.session_id = session_id
        self.expected = expected
        self.actual = actual


class ArtifactNotReadyError(Exception):
    def __init__(self, session_id: str, artifact: str):
        self.session_id = session_id
        self.artifact = artifact


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SessionNotFoundError)
    async def _session_not_found(request: Request, exc: SessionNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": f"Session '{exc.session_id}' not found."},
        )

    @app.exception_handler(InvalidTransitionError)
    async def _invalid_transition(request: Request, exc: InvalidTransitionError):
        return JSONResponse(
            status_code=409,
            content={
                "detail": (
                    f"Session '{exc.session_id}' is at status '{exc.actual}', "
                    f"expected '{exc.expected}'."
                )
            },
        )

    @app.exception_handler(ArtifactNotReadyError)
    async def _artifact_not_ready(request: Request, exc: ArtifactNotReadyError):
        return JSONResponse(
            status_code=409,
            content={
                "detail": f"'{exc.artifact}' is not ready yet for session '{exc.session_id}'."
            },
        )

    @app.exception_handler(Exception)
    async def _catch_all(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})
