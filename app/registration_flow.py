from __future__ import annotations

import secrets
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable


@dataclass
class MailDeliveryResult:
    delivered: bool
    mode: str
    target: str
    artifact_path: str = ''
    error: str = ''


def make_verification_code() -> str:
    return str(secrets.randbelow(900000) + 100000)


def normalize_recipients(raw: str | Iterable[str] | None) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        items = raw.replace(';', ',').split(',')
    else:
        items = list(raw)
    return [item.strip() for item in items if item and item.strip()]


def _render_email(subject: str, recipient: str, body: str, html: str | None = None, sender: str = 'noreply@tramplin.local') -> EmailMessage:
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = sender
    message['To'] = recipient
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype='html')
    return message


def send_email(app, recipient: str, subject: str, body: str, html: str | None = None) -> MailDeliveryResult:
    sender = app.config.get('MAIL_FROM', 'noreply@tramplin.local')
    message = _render_email(subject=subject, recipient=recipient, body=body, html=html, sender=sender)
    outbox_dir = Path(app.config.get('MAIL_OUTBOX_DIR', Path(app.root_path) / 'mail_outbox'))
    outbox_dir.mkdir(parents=True, exist_ok=True)
    host = app.config.get('MAIL_HOST', '').strip()

    if not host:
        filename = outbox_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{recipient.replace('@', '_at_')}.eml"
        filename.write_text(message.as_string(), encoding='utf-8')
        return MailDeliveryResult(delivered=True, mode='file', target=recipient, artifact_path=str(filename))

    port = int(app.config.get('MAIL_PORT', 587))
    username = app.config.get('MAIL_USERNAME', '').strip()
    password = app.config.get('MAIL_PASSWORD', '').strip()
    use_tls = str(app.config.get('MAIL_USE_TLS', 'true')).lower() in {'1', 'true', 'yes', 'on'}
    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls()
                smtp.ehlo()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return MailDeliveryResult(delivered=True, mode='smtp', target=recipient)
    except Exception as exc:  # pragma: no cover
        filename = outbox_dir / f"failed_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{recipient.replace('@', '_at_')}.eml"
        filename.write_text(message.as_string(), encoding='utf-8')
        return MailDeliveryResult(delivered=False, mode='fallback-file', target=recipient, artifact_path=str(filename), error=str(exc))


def notify_registration_started(app, *, user, flow, company_name: str, admin_recipients: list[str]) -> dict:
    user_subject = 'Трамплин: код подтверждения компании'
    user_body = (
        f'Здравствуйте, {user.display_name}!\n\n'
        f'Мы получили регистрацию компании {company_name}.\n'
        'Чтобы завершить регистрацию работодателя, введите этот код на странице подтверждения в Трамплине:\n\n'
        f'{flow.verification_code}\n\n'
        'Если вы не отправляли заявку, просто проигнорируйте это письмо.\n'
    )
    user_html = (
        f'<p>Здравствуйте, <strong>{user.display_name}</strong>!</p>'
        f'<p>Мы получили регистрацию компании <strong>{company_name}</strong>.</p>'
        '<p>Чтобы завершить регистрацию работодателя, введите код на странице подтверждения в Трамплине:</p>'
        f'<p style="font-size:28px;font-weight:800;letter-spacing:0.12em;">{flow.verification_code}</p>'
        '<p>Если вы не отправляли заявку, просто проигнорируйте это письмо.</p>'
    )
    user_result = send_email(app, flow.contact_email, user_subject, user_body, user_html)

    admin_results = []
    admin_subject = 'Новая регистрация работодателя в Трамплин'
    admin_body = (
        'Новый HR зарегистрирован на платформе.\n\n'
        f'Имя: {user.display_name}\n'
        f'Email: {user.email}\n'
        f'Компания: {company_name}\n'
        f'Код подтверждения: {flow.verification_code}\n'
        'Статус: ожидает ввода кода из письма.\n'
    )
    for recipient in admin_recipients:
        admin_results.append(send_email(app, recipient, admin_subject, admin_body))
    return {'user': user_result, 'admins': admin_results}


def notify_registration_confirmed(app, *, user, flow, company_name: str, admin_recipients: list[str]) -> dict:
    subject = 'Трамплин: регистрация подтверждена'
    body = (
        f'Здравствуйте, {user.display_name}!\n\n'
        'Код подтверждения принят, регистрация работодателя завершена.\n'
        f'Компания: {company_name}\n'
        'Теперь вы можете войти в платформу и продолжить работу.\n'
    )
    user_result = send_email(app, flow.contact_email, subject, body)

    admin_results = []
    admin_body = (
        'Регистрация работодателя подтверждена по email-коду.\n\n'
        f'Имя: {user.display_name}\n'
        f'Email: {user.email}\n'
        f'Компания: {company_name}\n'
        f'Код: {flow.verification_code}\n'
    )
    for recipient in admin_recipients:
        admin_results.append(send_email(app, recipient, 'Подтверждение регистрации HR', admin_body))
    return {'user': user_result, 'admins': admin_results}
