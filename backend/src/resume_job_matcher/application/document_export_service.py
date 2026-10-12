from datetime import UTC, datetime, timedelta
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_job_matcher.api.schemas import ResumeVersionContent
from resume_job_matcher.core.config import Settings
from resume_job_matcher.infrastructure.models import DocumentExport, ResumeVersion

EXPORT_TTL = timedelta(hours=24)


def cleanup_expired_exports(database_session: Session, settings: Settings) -> int:
    expired = list(
        database_session.execute(
            select(DocumentExport).where(DocumentExport.expires_at <= datetime.now(UTC))
        ).scalars()
    )
    for export in expired:
        (settings.generated_document_dir / export.storage_name).unlink(missing_ok=True)
        database_session.delete(export)
    if expired:
        database_session.commit()
    return len(expired)


def create_docx_export(
    database_session: Session, settings: Settings, version: ResumeVersion
) -> DocumentExport:
    cleanup_expired_exports(database_session, settings)
    content = ResumeVersionContent.model_validate(version.content)
    export = DocumentExport(
        user_id=version.user_id,
        resume_version_id=version.id,
        file_format="docx",
        storage_name=f"{version.id}.docx",
        download_name="resume.docx",
        expires_at=datetime.now(UTC) + EXPORT_TTL,
    )
    output_path = settings.generated_document_dir / export.storage_name
    render_docx(content, output_path)
    database_session.add(export)
    database_session.commit()
    return export


def render_docx(content: ResumeVersionContent, output_path: Path) -> None:
    """Render the immutable snapshot verbatim into one simple ATS-friendly document."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.15
    for section_index, section in enumerate(content.sections):
        paragraphs = []
        for line in section.source_text.splitlines():
            paragraphs.append(document.add_paragraph(line))
        if paragraphs and section_index != len(content.sections) - 1:
            paragraphs[-1].paragraph_format.space_after = Pt(8)
    document.core_properties.author = "Resume Job Matcher"
    document.core_properties.title = "Resume"
    document.save(str(output_path))
