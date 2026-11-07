"""
Фоновые задачи Celery.

generate_certificate_task — запускается при завершении студентом
курса (PATCH /enrollments/{id}/complete) и генерирует PDF-сертификат,
не блокируя ответ API.
"""

import logging
import os
import time
from datetime import datetime, timezone

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

CERTIFICATES_DIR = os.environ.get("CERTIFICATES_DIR", "certificates")
# Только для демонстрации KEDA: искусственная задержка, чтобы очередь
# успевала накапливаться (в production = 0).
SIMULATED_DELAY_SECONDS = float(os.environ.get("CERTIFICATE_DELAY_SECONDS", "0"))


def _upload_certificate_to_s3(file_path: str) -> str | None:
    """
    Кладёт готовый сертификат в S3 (SeaweedFS): certificates/<имя файла>.

    Включается S3_UPLOAD_CERTIFICATES=true (в Kubernetes — из ConfigMap
    s3-config). Сбой хранилища не должен ронять задачу: файл уже создан
    локально, поэтому ошибка только логируется.
    """
    if os.environ.get("S3_UPLOAD_CERTIFICATES", "false").lower() != "true":
        return None
    from app.s3_client import upload_file_sync

    key = f"certificates/{os.path.basename(file_path)}"
    try:
        with open(file_path, "rb") as f:
            content = f.read()
        ctype = "application/pdf" if file_path.endswith(".pdf") else "text/plain"
        upload_file_sync(content, key, ctype)
        return key
    except Exception as exc:  # noqa: BLE001
        logger.error("Не удалось загрузить %s в S3: %s", file_path, exc)
        return None


@celery_app.task(
    bind=True,
    name="tasks.generate_certificate",
    max_retries=3,
    default_retry_delay=30,
)
def generate_certificate_task(
    self,
    enrollment_id: int,
    student_name: str,
    course_title: str,
    grade: float,
) -> dict:
    """
    Генерирует PDF-сертификат о прохождении курса и сохраняет его на диск.

    Если библиотека reportlab не установлена, создаётся текстовая
    заглушка с тем же содержимым — это не мешает продемонстрировать
    сам механизм фоновой задачи (постановка в очередь, .delay(),
    повторные попытки при ошибке).
    """
    try:
        if SIMULATED_DELAY_SECONDS > 0:
            time.sleep(SIMULATED_DELAY_SECONDS)
        os.makedirs(CERTIFICATES_DIR, exist_ok=True)
        pdf_path = os.path.join(CERTIFICATES_DIR, f"certificate_{enrollment_id}.pdf")
        issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas

            c = canvas.Canvas(pdf_path, pagesize=A4)
            width, height = A4
            c.setFont("Helvetica-Bold", 24)
            c.drawCentredString(width / 2, height - 150, "СЕРТИФИКАТ")
            c.setFont("Helvetica", 16)
            c.drawCentredString(width / 2, height - 220, f"Выдан: {student_name}")
            c.drawCentredString(
                width / 2, height - 260, f"За успешное прохождение курса «{course_title}»"
            )
            c.drawCentredString(width / 2, height - 300, f"Оценка: {grade}")
            c.drawCentredString(width / 2, height - 340, f"Дата выдачи: {issued_at}")
            c.save()
            file_path = pdf_path

        except ImportError:
            logger.warning(
                "reportlab не установлен — создаётся текстовая заглушка сертификата"
            )
            file_path = pdf_path.replace(".pdf", ".txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(
                    "СЕРТИФИКАТ\n"
                    f"Выдан: {student_name}\n"
                    f"За успешное прохождение курса: {course_title}\n"
                    f"Оценка: {grade}\n"
                    f"Дата выдачи: {issued_at}\n"
                )

        logger.info(
            "Сертификат сгенерирован для enrollment_id=%s: %s", enrollment_id, file_path
        )
        s3_key = _upload_certificate_to_s3(file_path)
        return {
            "status": "generated",
            "enrollment_id": enrollment_id,
            "path": file_path,
            "s3_key": s3_key,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка генерации сертификата enrollment_id=%s: %s", enrollment_id, exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Письмо подтверждения email (лабораторная № 8, шаг 9)
# ---------------------------------------------------------------------------


def build_verification_email(email: str, token: str):
    """Собирает письмо (EmailMessage корректно кодирует кириллицу в UTF-8)."""
    from email.message import EmailMessage

    from app.config import email_token_hours, frontend_url, smtp_settings

    verify_url = f"{frontend_url()}/verify-email?token={token}"
    msg = EmailMessage()
    msg["Subject"] = "Подтвердите email — Образовательная платформа"
    msg["From"] = smtp_settings()["from"]
    msg["To"] = email
    msg.set_content(
        "Здравствуйте!\n\n"
        "Вы зарегистрировались на образовательной платформе. Чтобы активировать "
        "аккаунт, перейдите по ссылке:\n\n"
        f"{verify_url}\n\n"
        f"Ссылка действует {email_token_hours()} ч и работает один раз.\n"
        "Если вы не регистрировались — просто проигнорируйте это письмо.\n"
    )
    return msg, verify_url


@celery_app.task(bind=True, name="tasks.send_verification_email", max_retries=3)
def send_verification_email(self, email: str, token: str) -> dict:
    """
    Отправляет письмо через SMTP. Выполняется воркером в фоне: регистрация
    сразу отвечает 201, а письмо уходит позже. При недоступности SMTP —
    повтор с экспоненциальной задержкой 60 → 120 → 240 с.
    """
    import smtplib

    from app.config import smtp_settings

    cfg = smtp_settings()
    msg, verify_url = build_verification_email(email, token)
    if not cfg["host"]:
        # Режим разработки без почтового сервера: ссылка — в лог воркера.
        logger.warning("SMTP_HOST не задан. Ссылка подтверждения для %s: %s", email, verify_url)
        return {"status": "logged", "email": email}
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as smtp:
            if cfg["starttls"]:
                smtp.starttls()
            if cfg["user"]:
                smtp.login(cfg["user"], cfg["password"])
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        logger.error("Письмо для %s не отправлено: %s", email, exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    logger.info("Письмо подтверждения отправлено: %s", email)
    return {"status": "sent", "email": email}
