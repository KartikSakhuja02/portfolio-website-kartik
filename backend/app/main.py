import logging
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .models import ResumeDocument, UserStatus
from .schemas import AskRequest, AskResponse, AwsStatusResponse, DashboardMetricsResponse, Ec2LogsResponse, GitHubStatsResponse, HealthResponse, ResumeStatusResponse, ResumeUploadResponse, UserStatusResponse, UserStatusUpdateRequest
from .services.ai import generate_about_answer
from .services.resume import extract_text_from_upload, replace_active_resume, seed_default_resume
from .services.cloudwatch import get_all_dashboard_metrics
from .services.runtime_metrics import get_ec2_logs, record_request_event
from .dependencies import verify_admin


settings = get_settings()
logger = logging.getLogger("portfolio.api")
logger.setLevel(logging.INFO)
app_started_at = datetime.now(timezone.utc)

app = FastAPI(title="Portfolio AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


def get_active_resume(db: Session) -> ResumeDocument:
    return (
        db.query(ResumeDocument)
        .filter(ResumeDocument.is_active.is_(True))
        .order_by(ResumeDocument.created_at.desc())
        .first()
    )


def get_or_create_user_status(db: Session) -> UserStatus:
    status = db.query(UserStatus).first()
    if status is None:
        status = UserStatus(open_to_work=False)
        db.add(status)
        db.commit()
        db.refresh(status)
    return status


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    started_at = time.perf_counter()
    logger.info("request_started method=%s path=%s query=%s", request.method, request.url.path, request.url.query)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed method=%s path=%s", request.method, request.url.path)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        record_request_event(request.method, request.url.path, 500, elapsed_ms, request.url.query)
        raise

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    record_request_event(request.method, request.url.path, response.status_code, elapsed_ms, request.url.query)
    logger.info(
        "request_finished method=%s path=%s status=%s duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.on_event("startup")
def startup_event() -> None:
    logger.info("startup_begin database_url=%s openai_model=%s", settings.database_url, settings.openai_model)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        resume = seed_default_resume(db)
        logger.info("startup_resume_seeded filename=%s active=%s", resume.filename, resume.is_active)
    finally:
        db.close()
    logger.info("startup_complete")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    uptime_seconds = int((datetime.now(timezone.utc) - app_started_at).total_seconds())
    logger.info("health_check_ok uptime_seconds=%s", uptime_seconds)
    return HealthResponse(status="ok", started_at=app_started_at, uptime_seconds=uptime_seconds)


@app.get("/api/resume", response_model=ResumeStatusResponse)
def get_resume_status(db: Session = Depends(get_db)) -> ResumeStatusResponse:
    resume = (
        db.query(ResumeDocument)
        .filter(ResumeDocument.is_active.is_(True))
        .order_by(ResumeDocument.created_at.desc())
        .first()
    )

    if resume is None:
        return ResumeStatusResponse(has_resume=False)

    return ResumeStatusResponse(
        has_resume=True,
        filename=resume.filename,
        uploaded_at=resume.created_at,
    )


@app.get("/api/github-stats", response_model=GitHubStatsResponse)
def get_github_stats(year: int = None) -> GitHubStatsResponse:
    # Import the GitHub helper lazily so the API can start even if the
    # github service module has a syntax/indentation problem during development.
    from .services.github import get_github_commit_total, get_github_commit_for_year

    if year:
        commit_total, updated_at = get_github_commit_for_year(year)
    else:
        commit_total, updated_at = get_github_commit_total()
    return GitHubStatsResponse(
        username=settings.github_username,
        total_commit_contributions=commit_total,
        source="GitHub GraphQL",
        updated_at=updated_at,
    )


@app.get("/api/aws-status", response_model=AwsStatusResponse)
def get_aws_status() -> AwsStatusResponse:
    checked_at = datetime.now(timezone.utc)
    try:
        session = boto3.Session(region_name=settings.aws_region)
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        region = sts.meta.region_name or settings.aws_region
        return AwsStatusResponse(
            connected=True,
            provider="AWS STS",
            region=region,
            account_id=identity.get("Account"),
            arn=identity.get("Arn"),
            user_id=identity.get("UserId"),
            message="Connected to AWS with valid credentials.",
            checked_at=checked_at,
        )
    except (NoCredentialsError, ClientError, BotoCoreError) as exc:
        logger.warning("aws_status_unavailable error=%s", exc)
        return AwsStatusResponse(
            connected=False,
            provider="AWS STS",
            region=settings.aws_region,
            message="AWS credentials are not configured yet. Add AWS credentials or use an IAM role.",
            checked_at=checked_at,
        )


@app.get("/api/dashboard-metrics", response_model=DashboardMetricsResponse)
def get_dashboard_metrics() -> DashboardMetricsResponse:
    """Fetch real-time CloudWatch metrics for the dashboard.
    
    Returns CPU utilization, network metrics, and request counts.
    Uses AWS_EC2_INSTANCE_ID and AWS_LB_NAME from environment configuration.
    Note: This endpoint queries CloudWatch for the last 5 minutes of data.
    """
    metrics = get_all_dashboard_metrics(
        instance_id=settings.aws_ec2_instance_id or None,
        load_balancer_name=settings.aws_lb_name or None,
    )
    logger.info("dashboard_metrics_fetched", extra={"metrics": str(metrics)})
    return DashboardMetricsResponse(**metrics)


@app.get("/api/ec2-logs", response_model=Ec2LogsResponse)
def get_ec2_logs_endpoint(limit: int = 12) -> Ec2LogsResponse:
    """Return recent EC2 host/app log entries for the dashboard."""
    safe_limit = max(1, min(limit, 40))
    return Ec2LogsResponse(**get_ec2_logs(limit=safe_limit))


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(verify_admin), ) -> ResumeUploadResponse:
    file_bytes = await file.read()
    logger.info(
        "resume_upload_received filename=%s content_type=%s size_bytes=%s",
        file.filename,
        file.content_type,
        len(file_bytes),
    )
    try:
        content_text = extract_text_from_upload(file.filename or "resume", file.content_type or "", file_bytes)
    except ValueError as exc:
        logger.exception("resume_upload_failed filename=%s", file.filename)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resume = replace_active_resume(
        db,
        filename=file.filename or "resume",
        content_type=file.content_type or "application/octet-stream",
        content_text=content_text,
    )

    return ResumeUploadResponse(message="Resume uploaded and activated.", filename=resume.filename)


@app.get("/api/user-status", response_model=UserStatusResponse)
def get_user_status(db: Session = Depends(get_db)) -> UserStatusResponse:
    status = get_or_create_user_status(db)
    logger.info("user_status_retrieved open_to_work=%s", status.open_to_work)
    return UserStatusResponse(open_to_work=status.open_to_work, updated_at=status.updated_at)


@app.post("/api/user-status")
def update_user_status(payload: UserStatusUpdateRequest, db: Session = Depends(get_db), _=Depends(verify_admin)) -> UserStatusResponse:
    status = get_or_create_user_status(db)
    status.open_to_work = payload.open_to_work
    db.commit()
    db.refresh(status)
    logger.info("user_status_updated open_to_work=%s", status.open_to_work)
    return UserStatusResponse(open_to_work=status.open_to_work, updated_at=status.updated_at)


@app.post("/api/ask-ai", response_model=AskResponse)
def ask_ai(payload: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    logger.info("ask_ai_received question_length=%s", len(payload.question.strip()))
    resume = (
        db.query(ResumeDocument)
        .filter(ResumeDocument.is_active.is_(True))
        .order_by(ResumeDocument.created_at.desc())
        .first()
    )
    if resume is None:
        logger.info("ask_ai_no_active_resume_seeded")
        resume = seed_default_resume(db)

    try:
        answer = generate_about_answer(question=payload.question, resume_text=resume.content_text)
    except RuntimeError as exc:
        logger.exception("ask_ai_failed openai_model=%s resume_source=%s", settings.openai_model, resume.filename)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    logger.info("ask_ai_answered resume_source=%s answer_length=%s", resume.filename, len(answer))

    return AskResponse(answer=answer, model=settings.openai_model, resume_source=resume.filename)


@app.get("/{path:path}")
async def serve_spa(path: str):
    return FileResponse("static/index.html")
