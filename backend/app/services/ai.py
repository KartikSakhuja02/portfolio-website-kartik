import logging

from openai import OpenAI
from openai import APIConnectionError, APIError, APIStatusError, RateLimitError

from ..config import get_settings


logger = logging.getLogger("portfolio.api.ai")
logger.setLevel(logging.INFO)


def generate_about_answer(*, question: str, resume_text: str) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        logger.error("openai_key_missing")
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    default_headers: dict[str, str] = {}
    if "openrouter.ai" in settings.openai_base_url:
        if settings.openrouter_site_url:
            default_headers["HTTP-Referer"] = settings.openrouter_site_url
        if settings.openrouter_app_name:
            default_headers["X-Title"] = settings.openrouter_app_name

    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        default_headers=default_headers if default_headers else None,
    )

    clipped_resume = resume_text[:12000]
    logger.info(
        "openai_request_start model=%s base_url=%s question_length=%s resume_length=%s",
        settings.openai_model,
        settings.openai_base_url,
        len(question),
        len(clipped_resume),
    )
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            max_tokens=settings.openai_max_tokens,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Kartik Sakhuja's portfolio assistant. Answer questions about Kartik using only the resume text provided. "
                        "If the resume does not support an answer, say so clearly. Keep the tone professional, concise, and useful."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Resume text:\n{clipped_resume}\n\nQuestion:\n{question}",
                },
            ],
        )
    except APIStatusError as exc:
        if exc.status_code == 402:
            logger.exception("openrouter_insufficient_credits model=%s", settings.openai_model)
            raise RuntimeError(
                "OpenRouter credits are insufficient for this request. Add credits or lower OPENAI_MAX_TOKENS in .env."
            ) from exc
        logger.exception("openai_status_error model=%s status_code=%s", settings.openai_model, exc.status_code)
        raise RuntimeError(f"OpenAI API status error ({exc.status_code}): {exc}") from exc
    except RateLimitError as exc:
        logger.exception("openai_rate_limited model=%s", settings.openai_model)
        raise RuntimeError("OpenAI quota or billing limit reached. Check your OpenAI plan and billing details.") from exc
    except APIConnectionError as exc:
        logger.exception("openai_connection_failed model=%s", settings.openai_model)
        raise RuntimeError("OpenAI connection failed. Check network access and OpenAI endpoint reachability.") from exc
    except APIError as exc:
        logger.exception("openai_api_error model=%s", settings.openai_model)
        raise RuntimeError(f"OpenAI API error: {exc}") from exc

    message = response.choices[0].message.content
    logger.info("openai_request_complete model=%s has_content=%s", settings.openai_model, bool(message))
    return (message or "").strip()
