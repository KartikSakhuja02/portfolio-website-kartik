import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from ..config import get_settings
from .runtime_metrics import get_memory_usage, get_request_traffic_history, get_request_volume

logger = logging.getLogger("portfolio.cloudwatch")
settings = get_settings()


def get_cloudwatch_client():
    """Create a CloudWatch client with configured AWS credentials."""
    try:
        session = boto3.Session(region_name=settings.aws_region)
        return session.client("cloudwatch")
    except (NoCredentialsError, ClientError) as exc:
        logger.error("Failed to create CloudWatch client: %s", exc)
        return None


def _metric_time_window(period_minutes: int) -> tuple[datetime, datetime]:
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=period_minutes)
    return start_time, end_time


def _get_metric_statistics(client, *, namespace: str, metric_name: str, dimensions: list[dict], period_minutes: int, period: int, statistics: list[str], unit: str | None = None):
    start_time, end_time = _metric_time_window(period_minutes)
    query = {
        "Namespace": namespace,
        "MetricName": metric_name,
        "Dimensions": dimensions,
        "StartTime": start_time,
        "EndTime": end_time,
        "Period": period,
        "Statistics": statistics,
    }
    if unit is not None:
        query["Unit"] = unit

    return client.get_metric_statistics(**query), end_time


def get_ec2_cpu_utilization(instance_id: str | None = None, period_minutes: int = 5) -> dict:
    """Fetch EC2 CPU utilization from CloudWatch."""
    client = get_cloudwatch_client()
    if not client:
        return {"value": None, "unit": "%", "error": "CloudWatch not available"}

    try:
        response, end_time = _get_metric_statistics(
            client,
            namespace="AWS/EC2",
            metric_name="CPUUtilization",
            dimensions=[{"Name": "InstanceId", "Value": instance_id or "i-demo"}] if instance_id else [],
            period_minutes=period_minutes,
            period=300,
            statistics=["Average"],
            unit="Percent",
        )

        if response.get("Datapoints"):
            latest = sorted(response["Datapoints"], key=lambda x: x["Timestamp"])[-1]
            return {
                "value": round(latest["Average"], 1),
                "unit": "%",
                "timestamp": latest["Timestamp"],
                "error": None,
            }
        return {"value": 0.0, "unit": "%", "error": None, "timestamp": end_time}
    except (ClientError, BotoCoreError) as exc:
        logger.warning("Failed to fetch EC2 CPU utilization: %s", exc)
        return {"value": None, "unit": "%", "error": str(exc)}


def get_network_metrics(instance_id: str | None = None, period_minutes: int = 5) -> dict:
    """Fetch EC2 network metrics from CloudWatch."""
    client = get_cloudwatch_client()
    if not client:
        return {
            "inbound_bytes": None,
            "outbound_bytes": None,
            "inbound_packets": None,
            "outbound_packets": None,
            "error": "CloudWatch not available",
        }

    try:
        metrics = {
            "NetworkIn": "inbound_bytes",
            "NetworkOut": "outbound_bytes",
            "NetworkPacketsIn": "inbound_packets",
            "NetworkPacketsOut": "outbound_packets",
        }
        result = {}

        for metric_name, key in metrics.items():
            try:
                response, _ = _get_metric_statistics(
                    client,
                    namespace="AWS/EC2",
                    metric_name=metric_name,
                    dimensions=[{"Name": "InstanceId", "Value": instance_id or "i-demo"}] if instance_id else [],
                    period_minutes=period_minutes,
                    period=300,
                    statistics=["Sum"],
                )

                if response.get("Datapoints"):
                    latest = sorted(response["Datapoints"], key=lambda x: x["Timestamp"])[-1]
                    result[key] = round(latest["Sum"], 0)
                else:
                    result[key] = 0
            except Exception:
                result[key] = None

        result["error"] = None
        return result
    except (ClientError, BotoCoreError) as exc:
        logger.warning("Failed to fetch network metrics: %s", exc)
        return {
            "inbound_bytes": None,
            "outbound_bytes": None,
            "inbound_packets": None,
            "outbound_packets": None,
            "error": str(exc),
        }


def get_request_count_metric(
    load_balancer_name: str | None = None, period_minutes: int = 5
) -> dict:
    """Fetch ALB/ELB request count from CloudWatch."""
    client = get_cloudwatch_client()
    if not client or not load_balancer_name:
        request_volume = get_request_volume(window_seconds=60)
        request_volume["source"] = "runtime"
        return request_volume

    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=period_minutes)

        response = client.get_metric_statistics(
            Namespace="AWS/ApplicationELB",
            MetricName="RequestCount",
            Dimensions=[
                {"Name": "LoadBalancer", "Value": load_balancer_name or "app/demo/123"}
            ] if load_balancer_name else [],
            StartTime=start_time,
            EndTime=end_time,
            Period=60,
            Statistics=["Sum"],
        )

        if response.get("Datapoints"):
            total = sum(dp["Sum"] for dp in response["Datapoints"])
            requests_per_sec = total / (period_minutes * 60) if period_minutes > 0 else 0
            return {
                "request_count": total,
                "requests_per_second": round(requests_per_sec, 1),
                "unit": "count",
                "timestamp": end_time,
                "source": "cloudwatch",
                "error": None,
            }
        request_volume = get_request_volume(window_seconds=60)
        request_volume["source"] = "runtime"
        request_volume["error"] = None
        return request_volume
    except (ClientError, BotoCoreError) as exc:
        logger.warning("Failed to fetch request count metric: %s", exc)
        request_volume = get_request_volume(window_seconds=60)
        request_volume["source"] = "runtime"
        request_volume["error"] = str(exc)
        return request_volume


def get_memory_metrics() -> dict:
    """Fetch EC2 memory usage from the host runtime."""
    return get_memory_usage()


def get_all_dashboard_metrics(instance_id: str | None = None, load_balancer_name: str | None = None) -> dict:
    """Fetch all dashboard metrics in one call."""
    return {
        "cpu_utilization": get_ec2_cpu_utilization(instance_id),
        "memory_metrics": get_memory_metrics(),
        "network_metrics": get_network_metrics(instance_id),
        "request_metrics": get_request_count_metric(load_balancer_name),
        "traffic_history": get_request_traffic_history(),
        "timestamp": datetime.now(timezone.utc),
    }
