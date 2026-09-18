from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.core.auth import LOGIN_URL, NotAuthenticatedError
from app.core.config import settings
from app.web.routes.auth import router as auth_router
from app.web.routes.overview import router as overview_router

app = FastAPI(title="OneView Learning Analytics")

# The session cookie is signed (not encrypted) with SECRET_KEY: it carries only
# student_id, and the signature is what stops a caller choosing whose data they
# load. SECRET_KEY must be a real generated value in any deployed environment.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    # Secure cookies need TLS, which local dev does not have. Same notion of
    # "local" as the SECRET_KEY startup guard, so the two cannot drift apart.
    https_only=not settings.is_local,
)

app.include_router(auth_router)
app.include_router(overview_router)


@app.exception_handler(NotAuthenticatedError)
async def redirect_to_login(request: Request, exc: NotAuthenticatedError) -> RedirectResponse:
    """Anonymous callers of a protected route land on the login page."""
    return RedirectResponse(url=LOGIN_URL, status_code=303)
