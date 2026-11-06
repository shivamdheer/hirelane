"""The FastAPI application. Pages read the same SQLite database and fact bank the command line uses."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..config import Paths, get_paths
from ..db import DB
from . import security

HERE = Path(__file__).parent
NAV = (("/", "Home"), ("/needs", "Needs you"), ("/applications", "Applications"), ("/studio", "Resume studio"))


def create_app(paths: Paths | None = None) -> FastAPI:
    app = FastAPI(title="hirelane", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.paths = paths or get_paths()
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Response:
        path = request.url.path
        open_paths = ("/login", "/healthz") + (("/static/style.css",) if path.startswith("/static/") else ())
        if request.method == "POST" and not security.same_origin(request.headers.get("origin"),
                                                                 request.headers.get("host")):
            return JSONResponse({"error": "cross-site request refused"}, status_code=403)
        if path not in open_paths and not path.startswith("/static/") and not security.cookie_valid(
                request.cookies.get(security.COOKIE)):
            return RedirectResponse("/login", status_code=303)
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def get_db(request: Request) -> Iterator[DB]:
        db = DB(request.app.state.paths.db)
        try:
            yield db
        finally:
            db.close()

    app.state.get_db = get_db

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request) -> Response:
        return render(request, "login.html", "Sign in", "")

    @app.post("/login")
    def login(request: Request, token: str = Form("")) -> Response:
        if not security.token_matches(token):
            return render(request, "login.html", "Sign in", "", error="That token is not right.", status=401)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(security.COOKIE, security.issue_cookie(), httponly=True, samesite="strict",
                            max_age=security.SESSION_MAX_AGE_S)
        return response

    def render(request: Request, template: str, title: str, active: str, status: int = 200,
               **ctx: Any) -> Response:
        flash = request.query_params.get("msg", "")[:200]
        return templates.TemplateResponse(
            request, template, {"title": title, "active": active, "nav": NAV, "flash": flash, **ctx},
            status_code=status)

    app.state.render = render
    _register_pages(app, get_db)
    return app


def _register_pages(app: FastAPI, get_db: Any) -> None:
    """Page routes live in views.py so the logic can be tested without HTTP."""
    from . import views
    views.register(app, get_db)


def require_job(db: DB, key: str) -> Any:
    job = db.get_job(key)
    if job is None:
        raise HTTPException(status_code=404, detail="no such job")
    return job


__all__ = ["Depends", "create_app", "require_job"]
