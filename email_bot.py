"""Herramientas para analizar un buzón de correo IMAP y generar reportes."""
from __future__ import annotations

import imaplib
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import Iterable, List, Optional, Sequence, Tuple

import pandas as pd
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)


@dataclass
class EmailRecord:
    """Representa la información relevante de un correo electrónico."""

    uid: str
    subject: str
    sender: str
    date_received: Optional[datetime]
    due_date: Optional[datetime]
    priority: str
    read_status: str
    pending_task: bool

    @property
    def sort_key(self) -> Tuple[int, datetime]:
        # Los no leídos primero (0), luego leídos (1); fecha más reciente primero
        read_weight = 1 if self.read_status == "Leído" else 0
        return (read_weight, self.date_received or datetime.min)


class EmailInboxAnalyzer:
    """Encapsula la lógica para conectarse al buzón y generar reportes."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        mailbox: str = "INBOX",
        ssl: bool = True,
        port: Optional[int] = None,
    ) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.mailbox = mailbox
        self.ssl = ssl
        self.port = port
        self._connection: Optional[imaplib.IMAP4] = None

    def __enter__(self) -> "EmailInboxAnalyzer":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        """Establece la conexión IMAP."""
        if self.ssl:
            port = self.port or 993
            connection = imaplib.IMAP4_SSL(self.host, port)
        else:
            port = self.port or 143
            connection = imaplib.IMAP4(self.host, port)
        connection.login(self.username, self.password)
        self._connection = connection
        logger.info("Conectado a %s", self.host)

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.logout()
            finally:
                self._connection = None

    @property
    def connection(self) -> imaplib.IMAP4:
        if self._connection is None:
            raise RuntimeError("No hay conexión IMAP activa. Llame a connect() primero.")
        return self._connection

    def fetch_messages(self, limit: Optional[int] = None) -> List[EmailRecord]:
        """Obtiene mensajes desde el buzón y los transforma en registros."""
        self.connection.select(self.mailbox)
        status, data = self.connection.search(None, "ALL")
        if status != "OK":
            raise RuntimeError("No se pudo listar los mensajes del buzón")

        message_uids = data[0].split()
        if limit:
            message_uids = message_uids[-limit:]

        records: List[EmailRecord] = []
        for uid in message_uids:
            uid_str = uid.decode()
            record = self._fetch_single_message(uid_str)
            if record:
                records.append(record)
        records.sort(key=lambda r: (r.sort_key[0], r.sort_key[1]), reverse=True)
        return records

    def _fetch_single_message(self, uid: str) -> Optional[EmailRecord]:
        status, data = self.connection.uid("FETCH", uid, "(BODY.PEEK[] FLAGS)")
        if status != "OK" or not data:
            logger.warning("No se pudo obtener el mensaje %s", uid)
            return None

        raw_email = None
        flags: Sequence[bytes] = []
        for response_part in data:
            if isinstance(response_part, tuple):
                metadata, content = response_part
                raw_email = content
                flags = self._parse_flags(metadata)
        if raw_email is None:
            return None

        message = BytesParser(policy=policy.default).parsebytes(raw_email)
        subject = self._decode_header(message.get("Subject", "(Sin asunto)"))
        sender = self._decode_header(message.get("From", "Desconocido"))
        date_received = self._parse_date_header(message.get("Date"))
        body_text = self._extract_text(message)

        due_date = self._extract_due_date(message, body_text)
        priority = self._extract_priority(message, body_text)
        read_status = "Leído" if self._is_read(flags) else "No leído"
        pending_task = self._has_pending_task(body_text, subject)

        return EmailRecord(
            uid=uid,
            subject=subject,
            sender=sender,
            date_received=date_received,
            due_date=due_date,
            priority=priority,
            read_status=read_status,
            pending_task=pending_task,
        )

    @staticmethod
    def _parse_flags(metadata: bytes) -> Sequence[bytes]:
        match = re.search(rb"FLAGS \(([^)]*)\)", metadata)
        if not match:
            return []
        flags_raw = match.group(1)
        return [flag.strip() for flag in flags_raw.split() if flag]

    @staticmethod
    def _decode_header(value: str) -> str:
        from email.header import decode_header

        decoded_parts: List[str] = []
        for part, encoding in decode_header(value):
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                decoded_parts.append(part)
        return "".join(decoded_parts).strip()

    @staticmethod
    def _parse_date_header(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                return dt
            return dt.astimezone()
        except (TypeError, ValueError):
            try:
                return dateparser.parse(value)
            except (ValueError, TypeError, OverflowError):
                logger.debug("No se pudo interpretar la fecha: %s", value)
                return None

    @staticmethod
    def _is_read(flags: Sequence[bytes]) -> bool:
        return any(flag.decode().upper() == "\\SEEN" for flag in flags)

    @staticmethod
    def _extract_text(message: Message) -> str:
        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                disposition = (part.get("Content-Disposition") or "").lower()
                if content_type == "text/plain" and "attachment" not in disposition:
                    return part.get_content().strip()
            for part in message.walk():
                if part.get_content_type() == "text/html":
                    try:
                        from bs4 import BeautifulSoup  # type: ignore

                        soup = BeautifulSoup(part.get_content(), "html.parser")
                        return soup.get_text(" ", strip=True)
                    except Exception:
                        continue
            return ""
        return message.get_content().strip()

    @staticmethod
    def _extract_due_date(message: Message, body_text: str) -> Optional[datetime]:
        header_due = message.get("Reply-By") or message.get("X-Response-Due")
        if header_due:
            parsed = EmailInboxAnalyzer._safe_parse_datetime(header_due)
            if parsed:
                return parsed

        patterns = [
            r"(?:vencimiento|vence|antes del|deadline|due(?:\s+date)?|fecha\s+límite)[:\s-]+(\d{4}-\d{2}-\d{2})",
            r"(?:vencimiento|vence|antes del|deadline|due(?:\s+date)?|fecha\s+límite)[:\s-]+(\d{1,2}/\d{1,2}/\d{2,4})",
            r"\b(\d{4}-\d{2}-\d{2})\b",
            r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, body_text, flags=re.IGNORECASE)
            if match:
                parsed = EmailInboxAnalyzer._safe_parse_datetime(match.group(1))
                if parsed:
                    return parsed
        return None

    @staticmethod
    def _safe_parse_datetime(value: str) -> Optional[datetime]:
        try:
            parsed = dateparser.parse(value, dayfirst=True)
            if parsed is None:
                return None
            if parsed.tzinfo is None:
                return parsed
            return parsed.astimezone()
        except (ValueError, TypeError, OverflowError):
            return None

    @staticmethod
    def _extract_priority(message: Message, body_text: str) -> str:
        priority_header = (
            message.get("X-Priority")
            or message.get("Priority")
            or message.get("Importance")
            or ""
        ).lower()
        if "1" in priority_header or "high" in priority_header or "urgent" in priority_header:
            return "Alta"
        if "5" in priority_header or "low" in priority_header:
            return "Baja"

        subject = EmailInboxAnalyzer._decode_header(message.get("Subject", ""))
        text_to_check = f"{subject}\n{body_text}".lower()
        high_keywords = ["urgente", "asap", "importante", "prioridad", "accion requerida"]
        low_keywords = ["sin prisa", "cuando puedas", "baja prioridad"]
        if any(keyword in text_to_check for keyword in high_keywords):
            return "Alta"
        if any(keyword in text_to_check for keyword in low_keywords):
            return "Baja"
        return "Normal"

    @staticmethod
    def _has_pending_task(body_text: str, subject: str) -> bool:
        keywords = [
            "tarea",
            "pendiente",
            "por favor",
            "se requiere",
            "favor de",
            "accion",
            "acción",
            "follow up",
            "recordatorio",
        ]
        hay_solicitud = any(keyword in body_text.lower() for keyword in keywords)
        hay_en_asunto = any(keyword in subject.lower() for keyword in keywords)
        return hay_solicitud or hay_en_asunto

    def to_dataframe(self, records: Iterable[EmailRecord]) -> pd.DataFrame:
        data = [
            {
                "UID": record.uid,
                "Asunto": record.subject,
                "Remitente": record.sender,
                "Fecha de recepción": record.date_received,
                "Fecha de vencimiento": record.due_date,
                "Prioridad": record.priority,
                "Estado": record.read_status,
                "Pendiente": "Sí" if record.pending_task else "No",
            }
            for record in records
        ]
        df = pd.DataFrame(data)
        if not df.empty:
            df.sort_values(
                by=["Estado", "Fecha de recepción"],
                ascending=[True, False],
                inplace=True,
            )
        return df

    def export_to_excel(self, records: Sequence[EmailRecord], output_path: str) -> str:
        df = self.to_dataframe(records)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        df.to_excel(output_path, index=False)
        logger.info("Reporte guardado en %s", output_path)
        return output_path


__all__ = ["EmailInboxAnalyzer", "EmailRecord"]
