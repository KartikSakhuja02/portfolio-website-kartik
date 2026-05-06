import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from ..config import get_settings

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


def get_ec2_cpu_utilization(instance_id: str | None = None, period_minutes: int = 5) -> dict:
    """Fetch EC2 CPU utilization from CloudWatch."""
    client = get_cloudwatch_client()
    if not client:
        return {"value": None, "unit": "%", "error": "CloudWatch not available"}

    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=period_minutes)

        response = client.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[
                {"Name": "InstanceId", "Value": instance_id or "i-demo"}
            ] if instance_id else [],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,
            Statistics=["Average"],
            Unit="Percent",
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
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=period_minutes)

        metrics = {
            "NetworkIn": "inbound_bytes",
            "NetworkOut": "outbound_bytes",
            "NetworkPacketsIn": "inbound_packets",
            "NetworkPacketsOut": "outbound_packets",
        }
        result = {}

        for metric_name, key in metrics.items():
            try:
                response = client.get_metric_statistics(
                    Namespace="AWS/EC2",
                    MetricName=metric_name,
                    Dimensions=[
                        {"Name": "InstanceId", "Value": instance_id or "i-demo"}
                    ] if instance_id else [],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,
                    Statistics=["Sum"],
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
    if not client:
        return {"request_count": None, "unit": "count", "error": "CloudWatch not available"}

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
                "error": None,
            }
        return {
            "request_count": 0,
            "requests_per_second": 0,
            "unit": "count",
            "timestamp": end_time,
            "error": None,
        }
    except (ClientError, BotoCoreError) as exc:
        logger.warning("Failed to fetch request count metric: %s", exc)
        return {"request_count": None, "requests_per_second": None, "unit": "count", "error": str(exc)}


def get_all_dashboard_metrics(instance_id: str | None = None, load_balancer_name: str | None = None) -> dict:
    """Fetch all dashboard metrics in one call."""
    return {
        "cpu_utilization": get_ec2_cpu_utilization(instance_id),
        "network_metrics": get_network_metrics(instance_id),
        "request_metrics": get_request_count_metric(load_balancer_name),
        "timestamp": datetime.now(timezone.utc),
    }
