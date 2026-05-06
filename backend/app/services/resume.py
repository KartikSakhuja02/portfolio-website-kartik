from io import BytesIO

from pypdf import PdfReader
from sqlalchemy.orm import Session

from ..models import ResumeDocument


DEFAULT_RESUME_TEXT = (
    "Kartik Sakhuja is a Computer Science undergraduate specializing in cloud computing, "
    "focused on building scalable, real-world systems that integrate AI/ML, computer vision, "
    "and cloud infrastructure. He has hands-on experience developing end-to-end solutions "
    "from autonomous rover systems for grape detection with the Indian Council of Agricultural "
    "Research to IoT networks powered by AWS for real-time data processing. Alongside strong "
    "technical skills in TensorFlow, Docker, and modern backend frameworks, he has contributed "
    "to open-source through GirlScript Foundation and leads initiatives as Vice-President of his "
    "university's Cloud Computing Club, mentoring peers and driving practical cloud and DevOps learning."
)


def extract_text_from_upload(filename: str, content_type: str, data: bytes) -> str:
    if filename.lower().endswith(".pdf") or content_type == "application/pdf":
        reader = PdfReader(BytesIO(data))
        text_chunks = []
        for page in reader.pages:
            page_text = (page.extract_text() or "").strip()
            if page_text:
                text_chunks.append(page_text)

        text = "\n".join(text_chunks).strip()
        if not text:
            raise ValueError("No text could be extracted from the PDF.")
        return text

    try:
        return data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("Only UTF-8 text files or PDFs are supported.") from exc


def get_active_resume(db: Session) -> ResumeDocument | None:
    return (
        db.query(ResumeDocument)
        .filter(ResumeDocument.is_active.is_(True))
        .order_by(ResumeDocument.created_at.desc())
        .first()
    )


def seed_default_resume(db: Session) -> ResumeDocument:
    resume = get_active_resume(db)
    if resume is not None:
        return resume

    resume = ResumeDocument(
        title="Kartik Sakhuja Resume Summary",
        filename="seeded-resume-summary.txt",
        content_type="text/plain",
        content_text=DEFAULT_RESUME_TEXT,
        is_active=True,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def replace_active_resume(db: Session, *, filename: str, content_type: str, content_text: str) -> ResumeDocument:
    db.query(ResumeDocument).filter(ResumeDocument.is_active.is_(True)).update(
        {ResumeDocument.is_active: False}, synchronize_session=False
    )

    resume = ResumeDocument(
        title="Kartik Sakhuja Resume",
        filename=filename,
        content_type=content_type,
        content_text=content_text,
        is_active=True,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume
