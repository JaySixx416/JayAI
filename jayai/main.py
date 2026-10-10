import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from hmac import compare_digest
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from jayai.contracts import JobState, Limits, PolicyMode
from jayai.auth import (authorization_url, exchange_code, fetch_jwks, new_session_token,
                        oidc_settings, pkce_challenge, pkce_verifier, session_expiry,
                        session_token_hash, validate_id_token)
from jayai.db import Repository
from jayai.learning import LearningInput, routine_suggestions
from jayai.plans import expected_evidence, plan_digest, verify_read_only_result
from jayai.music import SongRequest, api_status as music_api_status, prepare_song

app = FastAPI(title="JayAI", version="0.25.0")


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    if os.getenv("JAYAI_ENV") != "development":
        raise HTTPException(status_code=503, detail="Development dashboard disabled")
    return HTMLResponse((Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8"))


@app.get("/music", response_class=HTMLResponse)
def music_studio() -> HTMLResponse:
    if os.getenv("JAYAI_ENV") != "development":
        raise HTTPException(status_code=503, detail="Development dashboard disabled")
    return HTMLResponse((Path(__file__).parent / "music.html").read_text(encoding="utf-8"))


class Health(BaseModel):
    status: str
    phase: int


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", phase=1)


def repository() -> Repository:
    return Repository()


SESSION_COOKIE = "jayai_session"
OIDC_STATE_COOKIE = "jayai_oidc_state"
OIDC_NONCE_COOKIE = "jayai_oidc_nonce"
OIDC_VERIFIER_COOKIE = "jayai_oidc_verifier"


def development_user(request: Request, x_jayai_key: str | None = Header(default=None)) -> UUID:
    """Authenticate the local development key or an expiring OIDC session."""
    if os.getenv("JAYAI_ENV") == "development":
        expected = os.getenv("JAYAI_DEV_API_KEY", "")
        user_id = os.getenv("JAYAI_DEV_USER_ID", "")
        if len(expected) >= 32 and user_id and x_jayai_key and compare_digest(x_jayai_key, expected):
            try:
                return UUID(user_id)
            except ValueError as exc:
                raise HTTPException(status_code=503, detail="Invalid development user configuration") from exc
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        if os.getenv("JAYAI_ENV") == "development":
            raise HTTPException(status_code=401, detail="Invalid API key")
        if not os.getenv("JAYAI_OIDC_ISSUER"):
            raise HTTPException(status_code=503, detail="OIDC authentication is not configured")
        raise HTTPException(status_code=401, detail="Authentication required")
    db = repository()
    row = db.get_auth_session(session_token_hash(token))
    if row is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        user_id = UUID(str(row["user_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Authentication required") from exc
    db.touch_auth_session(session_token_hash(token))
    return user_id


def _set_transient_cookie(response: JSONResponse, name: str, value: str, secure: bool) -> None:
    response.set_cookie(name, value, max_age=600, httponly=True, secure=secure,
                        samesite="lax", path="/auth")


@app.get("/auth/oidc/login")
def oidc_login() -> JSONResponse:
    try:
        settings = oidc_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="OIDC authentication is not configured") from exc
    state = new_session_token()
    nonce = new_session_token()
    verifier = pkce_verifier()
    url = authorization_url(settings.authorization_endpoint, settings.client_id,
                            settings.redirect_uri, state, nonce, pkce_challenge(verifier))
    response = JSONResponse({"authorization_url": url})
    _set_transient_cookie(response, OIDC_STATE_COOKIE, state, settings.cookie_secure)
    _set_transient_cookie(response, OIDC_NONCE_COOKIE, nonce, settings.cookie_secure)
    _set_transient_cookie(response, OIDC_VERIFIER_COOKIE, verifier, settings.cookie_secure)
    return response


@app.get("/auth/oidc/callback")
def oidc_callback(request: Request, code: str = "", state: str = "",
                  db: Repository = Depends(repository)) -> JSONResponse:
    try:
        settings = oidc_settings()
        expected_state = request.cookies.get(OIDC_STATE_COOKIE, "")
        nonce = request.cookies.get(OIDC_NONCE_COOKIE, "")
        verifier = request.cookies.get(OIDC_VERIFIER_COOKIE, "")
        if not code or not state or not expected_state or not compare_digest(state, expected_state):
            raise ValueError("Invalid OIDC state")
        if not nonce or not verifier:
            raise ValueError("OIDC login state expired")
        tokens = exchange_code(settings.token_endpoint, settings.client_id, settings.client_secret,
                               settings.redirect_uri, code, verifier)
        claims = validate_id_token(tokens["id_token"], fetch_jwks(settings.jwks_url),
                                   settings.issuer, settings.client_id, nonce)
        user_id = db.find_oidc_identity(claims["issuer"], claims["subject"])
        if user_id is None:
            bootstrap = os.getenv("JAYAI_OIDC_BOOTSTRAP_USER_ID", "")
            if not bootstrap:
                raise PermissionError("OIDC account is not linked")
            user_id = UUID(bootstrap)
            if not db.bind_oidc_identity(user_id, claims["issuer"], claims["subject"]):
                raise PermissionError("OIDC account is already linked")
        token = new_session_token()
        db.create_auth_session(user_id, session_token_hash(token), session_expiry())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="OIDC authentication failed") from exc
    response = JSONResponse({"authenticated": True})
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=settings.cookie_secure,
                        samesite="lax", path="/", max_age=43200)
    for name in (OIDC_STATE_COOKIE, OIDC_NONCE_COOKIE, OIDC_VERIFIER_COOKIE):
        response.delete_cookie(name, path="/auth")
    return response


@app.post("/auth/logout")
def logout(request: Request, db: Repository = Depends(repository)) -> JSONResponse:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.revoke_auth_session(session_token_hash(token))
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/api/music/status")
def music_status(user_id: UUID = Depends(development_user)) -> dict:
    return music_api_status()


@app.post("/api/music/prepare")
def music_prepare(body: SongRequest, user_id: UUID = Depends(development_user)) -> dict:
    try:
        return prepare_song(body).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=1, max_length=4000)
    limits: Limits = Field(default_factory=Limits)


class JobResponse(BaseModel):
    id: UUID
    goal: str
    state: JobState
    limits: Limits


@app.post("/jobs", response_model=JobResponse, status_code=201)
def create_job(body: JobCreate, user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> JobResponse:
    if not body.goal.strip():
        raise HTTPException(status_code=422, detail="Goal cannot be blank")
    job_id = db.create_job(user_id, body.goal, body.limits)
    return JobResponse(id=job_id, goal=body.goal, state=JobState.RECEIVED, limits=body.limits)


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID, user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> JobResponse:
    row = db.get_job(user_id, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(row)


@app.get("/jobs", response_model=list[JobResponse])
def list_jobs(user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> list[JobResponse]:
    return [JobResponse.model_validate(row) for row in db.list_jobs(user_id)]


@app.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: UUID, user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> JobResponse:
    row = db.get_job(user_id, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        if row["state"] == JobState.WAITING_FOR_APPROVAL.value:
            plan = db.get_plan(user_id, job_id)
            if plan is not None:
                digest = plan_digest(plan)
                atomic_reject = getattr(db, "reject_and_cancel_plan", None)
                if atomic_reject is not None:
                    atomic_reject(user_id, job_id, digest,
                                  "User cancelled the task during plan review")
                else:  # Compatibility for narrow in-memory test repositories.
                    db.record_approval_decision(user_id, job_id, digest, "REJECTED",
                                                "User cancelled the task during plan review")
                    db.transition_job(user_id, job_id, JobState.CANCELLED, "Cancelled by user")
            else:
                db.transition_job(user_id, job_id, JobState.CANCELLED, "Cancelled by user")
        else:
            db.transition_job(user_id, job_id, JobState.CANCELLED, "Cancelled by user")
    except (LookupError, ValueError, RuntimeError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    row = db.get_job(user_id, job_id)
    return JobResponse.model_validate(row)


@app.post("/control/pause")
def pause(user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    db.set_paused(user_id, True)
    return {"paused": True}


@app.post("/control/resume")
def resume(user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    db.set_paused(user_id, False)
    return {"paused": False}


@app.get("/control")
def control_status(user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    return {"paused": db.is_paused(user_id)}


@app.post("/jobs/{job_id}/plan")
def plan_job(job_id: UUID, user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    row = db.get_job(user_id, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["state"] not in (JobState.RECEIVED.value, JobState.PLANNING.value, JobState.WAITING_FOR_APPROVAL.value):
        raise HTTPException(status_code=409, detail="Job cannot accept a plan in its current state")
    if db.is_paused(user_id):
        raise HTTPException(status_code=409, detail="User actions paused")
    plan = db.get_plan(user_id, job_id)
    from jayai.planner import propose
    try:
        if plan is None:
            db.reserve_plan_request(user_id, job_id)
            try:
                plan = propose(row["goal"]).model_dump()
                plan["expected_evidence"] = expected_evidence(plan["action"])
                db.save_plan(user_id, job_id, plan)
            except Exception:
                db.finish_plan_request(user_id, job_id, False)
                raise
            db.finish_plan_request(user_id, job_id, True)
        # The authenticated request can make its plan reviewable without an
        # active Redis worker; a later queued delivery sees the new state.
        current = db.get_job(user_id, job_id)["state"]
        if current == JobState.RECEIVED.value:
            db.transition_job(user_id, job_id, JobState.PLANNING, "Review-only plan created")
        current = db.get_job(user_id, job_id)["state"]
        if current == JobState.PLANNING.value:
            db.transition_job(user_id, job_id, JobState.WAITING_FOR_APPROVAL, "Awaiting user review")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=503, detail="Local model returned an invalid plan") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {**plan, "sha256": plan_digest(plan)}


@app.get("/jobs/{job_id}/plan")
def get_job_plan(job_id: UUID, user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    plan = db.get_plan(user_id, job_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {**plan, "sha256": plan_digest(plan)}


class Approval(BaseModel):
    plan_sha256: str = Field(pattern="^[a-f0-9]{64}$")


class Rejection(BaseModel):
    plan_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    reason: str = Field(default="Rejected by user", min_length=1, max_length=500)


class PermissionGrant(BaseModel):
    resource: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_.-]*$")
    actions: list[str] = Field(min_length=1, max_length=16)
    mode: PolicyMode
    expires_in_seconds: int = Field(default=3600, ge=60, le=86400)

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, value):
        if len(set(value)) != len(value) or any(
            not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", action) for action in value
        ):
            raise ValueError("Actions must be unique lowercase identifiers")
        return value


@app.get("/permissions")
def get_permissions(user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> list[dict]:
    return db.list_permissions(user_id)


@app.post("/permissions", status_code=201)
def grant_permission(body: PermissionGrant, user_id: UUID = Depends(development_user),
                     db: Repository = Depends(repository)) -> dict:
    try:
        permission_id = db.set_permission(user_id, body.resource, body.actions, body.mode.value,
                                          body.expires_in_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": permission_id, "resource": body.resource, "actions": body.actions,
            "mode": body.mode.value, "expires_in_seconds": body.expires_in_seconds}


@app.delete("/permissions/{permission_id}")
def delete_permission(permission_id: UUID, user_id: UUID = Depends(development_user),
                      db: Repository = Depends(repository)) -> dict:
    if not db.revoke_permission(user_id, permission_id):
        raise HTTPException(status_code=404, detail="Permission not found")
    return {"revoked": True}


@app.get("/jobs/{job_id}/decision")
def get_job_decision(job_id: UUID, user_id: UUID = Depends(development_user),
                     db: Repository = Depends(repository)) -> dict:
    if db.get_job(user_id, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"decision": db.get_approval_decision(user_id, job_id)}


@app.post("/jobs/{job_id}/reject")
def reject_job_plan(job_id: UUID, body: Rejection, user_id: UUID = Depends(development_user),
                    db: Repository = Depends(repository)) -> dict:
    row = db.get_job(user_id, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    plan = db.get_plan(user_id, job_id)
    if plan is None or not compare_digest(plan_digest(plan), body.plan_sha256):
        raise HTTPException(status_code=409, detail="Plan digest does not match")
    try:
        atomic_reject = getattr(db, "reject_and_cancel_plan", None)
        if atomic_reject is not None:
            atomic_reject(user_id, job_id, body.plan_sha256, body.reason)
        else:  # Compatibility for narrow in-memory test repositories.
            decision = db.record_approval_decision(user_id, job_id, body.plan_sha256,
                                                   "REJECTED", body.reason)
            if row["state"] == JobState.WAITING_FOR_APPROVAL.value:
                db.transition_job(user_id, job_id, JobState.CANCELLED,
                                  "User rejected the reviewed plan")
            return {"decision": decision["decision"], "state": JobState.CANCELLED.value}
        return {"decision": "REJECTED", "state": JobState.CANCELLED.value}
    except (LookupError, ValueError, PermissionError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/run")
def run_approved_job(job_id: UUID, body: Approval, user_id: UUID = Depends(development_user),
                     db: Repository = Depends(repository)) -> dict:
    row = db.get_job(user_id, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    plan = db.get_plan(user_id, job_id)
    if row["state"] != JobState.WAITING_FOR_APPROVAL.value or plan is None:
        raise HTTPException(status_code=409, detail="Job has no plan awaiting approval")
    if not compare_digest(plan_digest(plan), body.plan_sha256):
        raise HTTPException(status_code=409, detail="Plan digest does not match")
    if plan.get("action") not in ("pc_health", "pc_processes"):
        raise HTTPException(status_code=409, detail="Plan has no executable read-only action")
    if db.is_paused(user_id):
        raise HTTPException(status_code=409, detail="User actions paused")
    try:
        atomic_admit = getattr(db, "admit_approved_plan", None)
        if atomic_admit is not None:
            atomic_admit(user_id, job_id, body.plan_sha256)
        else:  # Compatibility for narrow in-memory test repositories.
            db.record_approval_decision(user_id, job_id, body.plan_sha256, "APPROVED")
            db.transition_job(user_id, job_id, JobState.EXECUTING,
                              f"User approved plan {body.plan_sha256}")
    except (LookupError, ValueError, RuntimeError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        if plan["action"] == "pc_processes":
            from jayai.maintenance import running_processes
            report = running_processes()
        else:
            from jayai.maintenance import check, observe, state_path
            report = check()
        if not verify_read_only_result(plan["action"], report):
            raise ValueError("Read-only action returned incomplete or invalid verification evidence")
        if plan["action"] == "pc_health":
            from jayai.maintenance import observe, state_path
            report = observe(state_path(), report)
        db.transition_job(user_id, job_id, JobState.OBSERVING, "Read-only PC observation returned")
        db.transition_job(user_id, job_id, JobState.VERIFYING, "Read-only PC report shape verified")
        result = {"kind": plan["action"], "report": report}
        db.save_result(user_id, job_id, result)
        db.transition_job(user_id, job_id, JobState.COMPLETED, "Verified read-only PC result saved")
        return result
    except Exception:
        current = db.get_job(user_id, job_id)
        if current and current["state"] in (JobState.EXECUTING.value, JobState.OBSERVING.value, JobState.VERIFYING.value):
            db.transition_job(user_id, job_id, JobState.FAILED, "Approved PC health check failed")
        raise


@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: UUID, user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    result = db.get_result(user_id, job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


def learning_view(db: Repository, user_id: UUID) -> dict:
    data = db.list_learning(user_id)
    data["routine_suggestions"] = routine_suggestions(data["repeat_patterns"], data["episodes"])
    return data


@app.get("/learning")
def get_learning(user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    return learning_view(db, user_id)


@app.get("/learning/export")
def export_learning(user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> JSONResponse:
    """Export only the authenticated user's bounded learning records and suggestions."""
    return JSONResponse(
        content=jsonable_encoder({"schema_version": 1, "exported_at": datetime.now(timezone.utc),
                                  **learning_view(db, user_id)}),
        headers={"Content-Disposition": 'attachment; filename="jayai-learning-export.json"',
                 "Cache-Control": "no-store"},
    )


@app.get("/pc/history")
def get_pc_history(limit: int = 20, user_id: UUID = Depends(development_user)) -> dict:
    from jayai.maintenance import monitor_history
    try:
        return monitor_history(limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/learning/{record_key}")
def save_learning(record_key: str, body: LearningInput,
                  user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,63}", record_key):
        raise HTTPException(status_code=422, detail="Learning key must be a 2–64 character lowercase identifier")
    if body.source == "USER_CORRECTION":
        existing = db.list_learning(user_id)["records"]
        if not any(item["record_key"] == record_key for item in existing):
            raise HTTPException(status_code=404, detail="There is no saved record to correct")
    return db.save_learning(user_id, record_key, body.model_dump())


@app.delete("/learning")
def clear_learning(user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    return {"deleted": db.delete_learning(user_id)}


@app.delete("/learning/{record_key}")
def delete_learning(record_key: str, user_id: UUID = Depends(development_user),
                    db: Repository = Depends(repository)) -> dict:
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,63}", record_key):
        raise HTTPException(status_code=422, detail="Invalid learning key")
    return {"deleted": bool(db.delete_learning(user_id, record_key))}


class OAuthComplete(BaseModel):
    state: str = Field(min_length=1)
    code: str = Field(min_length=1)


@app.post("/connections/google/start")
def google_start(user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    from jayai.google import start
    return {"authorization_url": start(db, user_id)}


@app.get("/connections/google/callback")
def google_callback() -> dict:
    return {"message": "Copy the code and state from the address bar and submit them to the authenticated completion endpoint."}


@app.post("/connections/google/complete")
def google_complete(body: OAuthComplete, user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    from jayai.google import complete
    try:
        complete(db, user_id, body.state, body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"connected": True}


@app.delete("/connections/google")
def google_disconnect(user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    from jayai.google import disconnect
    return {"disconnected": disconnect(db, user_id)}


@app.get("/connections/google/{kind}")
def google_read(kind: str, user_id: UUID = Depends(development_user), db: Repository = Depends(repository)) -> dict:
    from jayai.google import read_items
    if kind not in ("mail", "calendar"):
        raise HTTPException(status_code=404, detail="Collection not found")
    try:
        return read_items(db, user_id, kind)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
