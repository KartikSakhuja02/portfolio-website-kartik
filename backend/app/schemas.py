from datetime import datetime

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class AskResponse(BaseModel):
    answer: str
    model: str
    resume_source: str


class ResumeUploadResponse(BaseModel):
    message: str
    filename: str


class ResumeStatusResponse(BaseModel):
    has_resume: bool
    filename: str | None = None
    uploaded_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
    started_at: datetime
    uptime_seconds: int


class GitHubStatsResponse(BaseModel):
    username: str
    total_commit_contributions: int
    source: str
    updated_at: datetime


class AwsStatusResponse(BaseModel):
    connected: bool
    provider: str
    region: str
    account_id: str | None = None
    arn: str | None = None
    user_id: str | None = None
    message: str
    checked_at: datetime


class UserStatusResponse(BaseModel):
    open_to_work: bool
    updated_at: datetime


class UserStatusUpdateRequest(BaseModel):
    open_to_work: bool


class MetricValue(BaseModel):
    value: float | None = None
    unit: str
    timestamp: datetime | None = None
    error: str | None = None


class NetworkMetrics(BaseModel):
    inbound_bytes: float | None = None
    outbound_bytes: float | None = None
    inbound_packets: float | None = None
    outbound_packets: float | None = None
    error: str | None = None


class RequestMetrics(BaseModel):
    request_count: float | None = None
    requests_per_second: float | None = None
    unit: str
    timestamp: datetime | None = None
    source: str | None = None
    error: str | None = None


class MemoryMetrics(BaseModel):
    total_bytes: float | None = None
    used_bytes: float | None = None
    available_bytes: float | None = None
    percent_used: float | None = None
    unit: str
    timestamp: datetime | None = None
    error: str | None = None


class Ec2LogEntry(BaseModel):
    source: str
    message: str
    timestamp: datetime | None = None


class Ec2LogsResponse(BaseModel):
    entries: list[Ec2LogEntry]
    updated_at: datetime


class DashboardMetricsResponse(BaseModel):
    cpu_utilization: MetricValue
    memory_metrics: MemoryMetrics
    network_metrics: NetworkMetrics
    request_metrics: RequestMetrics
    timestamp: datetime
