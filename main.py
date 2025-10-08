#!/usr/bin/env python3
"""Herramienta de línea de comandos para generar reportes del inbox."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
from typing import Optional

from email_bot import EmailInboxAnalyzer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera un reporte en Excel del buzón IMAP con prioridades, fechas y pendientes."
        )
    )
    parser.add_argument("--host", default=os.getenv("EMAIL_HOST"), help="Servidor IMAP")
    parser.add_argument("--username", default=os.getenv("EMAIL_USER"), help="Usuario IMAP")
    parser.add_argument(
        "--password",
        default=os.getenv("EMAIL_PASSWORD"),
        help="Contraseña IMAP (si no se facilita se solicitará de forma interactiva)",
    )
    parser.add_argument("--mailbox", default=os.getenv("EMAIL_MAILBOX", "INBOX"), help="Buzón a revisar")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Número máximo de correos a procesar (por defecto todos)",
    )
    parser.add_argument(
        "--output",
        default="reportes/inbox_report.xlsx",
        help="Ruta del archivo Excel a generar",
    )
    parser.add_argument(
        "--no-ssl",
        action="store_true",
        help="Deshabilita SSL (no recomendado salvo servidores específicos)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Puerto IMAP. Se infiere automáticamente si no se indica.",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="Nivel de log (DEBUG, INFO, WARNING, ERROR)",
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def resolve_password(args: argparse.Namespace) -> str:
    if args.password:
        return args.password
    return getpass.getpass("Contraseña IMAP: ")


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    if not args.host or not args.username:
        raise SystemExit(
            "Debe proporcionar al menos el servidor (--host) y el usuario (--username) o configurar las variables de entorno EMAIL_HOST y EMAIL_USER."
        )

    password = resolve_password(args)

    ssl_enabled = not args.no_ssl

    logging.getLogger(__name__).info(
        "Generando reporte para %s en %s", args.username, args.mailbox
    )

    analyzer = EmailInboxAnalyzer(
        host=args.host,
        username=args.username,
        password=password,
        mailbox=args.mailbox,
        ssl=ssl_enabled,
        port=args.port,
    )

    with analyzer:
        records = analyzer.fetch_messages(limit=args.limit)
        output_path = analyzer.export_to_excel(records, args.output)
        logging.getLogger(__name__).info("Reporte generado: %s", output_path)


if __name__ == "__main__":
    main()
