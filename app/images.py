"""
Безопасная обработка загруженных аватаров (лабораторная № 8, шаг 8).

  1. Тип определяется по «магическим байтам», а не по расширению или
     Content-Type от клиента (их подделать проще всего).
  2. SVG отклоняется всегда: это XML, в котором может быть <script>, —
     классический stored XSS через «картинку».
  3. Картинка перекодируется Pillow в WebP 256×256: метаданные (EXIF с
     геолокацией!) отбрасываются, а файл-полиглот (картинка + HTML/JS в
     хвосте) превращается в чистые пиксели.
"""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

AVATAR_SIZE = 256
ALLOWED = {"image/jpeg", "image/png", "image/webp"}


def sniff_image_type(data: bytes) -> str | None:
    """MIME по сигнатуре файла или None."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def looks_like_svg(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith(b"<?xml") or b"<svg" in head


def process_avatar(data: bytes) -> bytes:
    """Проверяет и перекодирует аватар; ValueError с понятным сообщением при ошибке."""
    if looks_like_svg(data):
        raise ValueError("SVG не поддерживается (может содержать скрипты)")
    if sniff_image_type(data) not in ALLOWED:
        raise ValueError("Допустимы только JPEG, PNG и WebP")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Файл повреждён или не является изображением") from exc
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=85)  # метаданные не копируются
    return out.getvalue()
