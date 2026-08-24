"""Extracts usable text from PDF files and .eml emails."""
from __future__ import annotations

import email
import io
import logging
import re
from dataclasses import dataclass
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ExtractedContent:
    text: str
    """Full text sent to the LLM (subject + body + attachments)."""
    primary_source: Optional[Path]
    """Preferred file to link from the calendar entry (usually a PDF attachment)."""


class PdfTextExtractor:
    @staticmethod
    def extract(pdf_bytes: bytes) -> str:
        import pdfplumber

        pages = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return "\n".join(pages).strip()


class HtmlStripper:
    @staticmethod
    def to_text(html: str) -> str:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        text = re.sub(r"(?is)<br\s*/?>", "\n", text)
        text = re.sub(r"(?is)</p>", "\n\n", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = text.replace("&nbsp;", " ")
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()


class MimeDecoder:
    @staticmethod
    def decode(raw: Optional[str]) -> str:
        if not raw:
            return ""
        parts = decode_header(raw)
        return "".join(
            p.decode(enc or "utf-8", errors="replace") if isinstance(p, bytes) else p
            for p, enc in parts
        )


class ContentExtractor:
    """Reads a file from the inbox folder (.pdf or .eml) and returns the
    text that gets sent to the LLM for event detection."""

    def __init__(self, attachments_dir: Path):
        self._attachments_dir = attachments_dir
        self._pdf = PdfTextExtractor()
        self._html = HtmlStripper()
        self._mime = MimeDecoder()

    def extract(self, path: Path) -> ExtractedContent:
        if path.suffix.lower() == ".pdf":
            return self._extract_pdf(path)
        if path.suffix.lower() == ".eml":
            return self._extract_eml(path)
        raise ValueError(f"Unsupported file type: {path.suffix}")

    def _extract_pdf(self, path: Path) -> ExtractedContent:
        text = self._pdf.extract(path.read_bytes())
        logger.debug("Extracted %d chars of text from PDF %s", len(text), path.name)
        return ExtractedContent(text=f"[PDF: {path.name}]\n{text}", primary_source=None)

    def _extract_eml(self, path: Path) -> ExtractedContent:
        with open(path, "rb") as f:
            msg: Message = email.message_from_binary_file(f)

        subject = self._mime.decode(msg.get("Subject"))
        sender = self._mime.decode(msg.get("From"))
        date_hdr = msg.get("Date", "")

        body_text, body_html, attachments = self._walk_parts(msg, path.stem)

        if not body_text.strip() and body_html.strip():
            body_text = self._html.to_text(body_html)

        logger.debug(
            "Parsed email %s: subject=%r, %d attachment(s)",
            path.name, subject, len(attachments),
        )

        parts = [f"[EMAIL: {path.name}]", f"Subject: {subject}", f"From: {sender}",
                 f"Date: {date_hdr}", "", body_text.strip()]
        for attach_path in attachments:
            try:
                attach_text = self._pdf.extract(attach_path.read_bytes())
            except Exception:
                logger.warning("Could not extract text from attachment %s", attach_path.name, exc_info=True)
                attach_text = ""
            parts.append(f"\n[Attachment: {attach_path.name}]\n{attach_text}")

        primary_source = attachments[0] if attachments else None
        return ExtractedContent(text="\n".join(parts), primary_source=primary_source)

    def _walk_parts(self, msg: Message, stem: str) -> tuple[str, str, list[Path]]:
        body_text, body_html = "", ""
        attachments: list[Path] = []

        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")

            if content_type == "text/plain" and "attachment" not in disposition:
                body_text += self._decode_part(part)
            elif content_type == "text/html" and "attachment" not in disposition:
                body_html += self._decode_part(part)
            elif content_type == "application/pdf" or (
                part.get_filename() and part.get_filename().lower().endswith(".pdf")
            ):
                attachments.append(self._save_attachment(part, stem))

        return body_text, body_html, attachments

    @staticmethod
    def _decode_part(part: Message) -> str:
        charset = part.get_content_charset() or "utf-8"
        payload = part.get_payload(decode=True)
        if not payload:
            return ""
        try:
            return payload.decode(charset, errors="replace")
        except (LookupError, ValueError):
            return payload.decode("utf-8", errors="replace")

    def _save_attachment(self, part: Message, stem: str) -> Path:
        filename = self._mime.decode(part.get_filename() or "attachment.pdf")
        safe_name = re.sub(r"[^\w\-.]", "_", f"{stem}_{filename}")
        out_path = self._attachments_dir / safe_name
        out_path.write_bytes(part.get_payload(decode=True) or b"")
        return out_path
