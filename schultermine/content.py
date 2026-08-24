"""Extrahiert verwertbaren Text aus PDF-Dateien und .eml-E-Mails."""
from __future__ import annotations

import email
import io
import re
from dataclasses import dataclass
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import Optional


@dataclass
class ExtractedContent:
    text: str
    """Vollständiger Text, der ans LLM geschickt wird (Betreff+Body+Anhänge)."""
    primary_source: Optional[Path]
    """Bevorzugte Datei, auf die im Kalendereintrag verlinkt wird (meist ein PDF-Anhang)."""


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
    """Liest eine Datei aus dem Eingangsordner (.pdf oder .eml) und liefert den
    Text, den das LLM zur Terminerkennung bekommt."""

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
        raise ValueError(f"Nicht unterstützter Dateityp: {path.suffix}")

    def _extract_pdf(self, path: Path) -> ExtractedContent:
        text = self._pdf.extract(path.read_bytes())
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

        parts = [f"[E-MAIL: {path.name}]", f"Betreff: {subject}", f"Von: {sender}",
                 f"Datum: {date_hdr}", "", body_text.strip()]
        for attach_path in attachments:
            try:
                attach_text = self._pdf.extract(attach_path.read_bytes())
            except Exception:
                attach_text = ""
            parts.append(f"\n[Anhang: {attach_path.name}]\n{attach_text}")

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
        filename = self._mime.decode(part.get_filename() or "anhang.pdf")
        safe_name = re.sub(r"[^\w\-.]", "_", f"{stem}_{filename}")
        out_path = self._attachments_dir / safe_name
        out_path.write_bytes(part.get_payload(decode=True) or b"")
        return out_path
