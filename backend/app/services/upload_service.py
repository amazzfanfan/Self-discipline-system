import asyncio
import hashlib
import re
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from app.core.config import get_settings

settings = get_settings()
UPLOAD_DIRECTORY = Path("uploads").resolve()
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_EDGE = 4096
MIN_IMAGE_EDGE = 128
Image.MAX_IMAGE_PIXELS = 40_000_000


@dataclass(frozen=True)
class SavedImage:
    filename: str
    path: str
    url: str
    sha256: str
    quality: dict


def _image_extension(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    return None


def _normalize_image(content: bytes) -> tuple[bytes, dict]:
    """Decode and re-encode an upload to remove EXIF/GPS and parser payloads."""
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            if min(source.size) < MIN_IMAGE_EDGE:
                raise HTTPException(422, f"图片边长不能小于 {MIN_IMAGE_EDGE}px")
            image = ImageOps.exif_transpose(source)
            image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            grayscale = image.convert("L")
            brightness = float(ImageStat.Stat(grayscale).mean[0])
            contrast = float(ImageStat.Stat(grayscale).stddev[0])
            edge_variance = float(ImageStat.Stat(grayscale.filter(ImageFilter.FIND_EDGES)).var[0])
            warnings = []
            if brightness < 45:
                warnings.append("光线偏暗，建议面向自然光重拍")
            elif brightness > 220:
                warnings.append("照片可能过曝，建议降低光线强度")
            if contrast < 18:
                warnings.append("画面对比度较低，请确认镜头清晰且无遮挡")
            if edge_variance < 35:
                warnings.append("照片清晰度可能不足，请保持镜头稳定")
            quality = {
                "width": image.width,
                "height": image.height,
                "brightness": round(brightness, 1),
                "contrast": round(contrast, 1),
                "sharpness": round(edge_variance, 1),
                "acceptable": not warnings,
                "warnings": warnings,
            }
            output = BytesIO()
            image.save(output, format="JPEG", quality=90, optimize=True)
            return output.getvalue(), quality
    except HTTPException:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(415, "图片无法安全解码") from exc


async def save_image_upload(file: UploadFile, prefix: str) -> SavedImage:
    """Persist a bounded, signature-verified image under a generated filename."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, "仅支持 JPEG、PNG 或 WebP 图片")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    await file.close()
    if not content:
        raise HTTPException(400, "上传文件为空")
    if len(content) > max_bytes:
        raise HTTPException(413, f"图片不能超过 {settings.MAX_UPLOAD_SIZE_MB}MB")

    if not _image_extension(content):
        raise HTTPException(415, "图片内容与支持的格式不匹配")

    normalized, quality = await asyncio.to_thread(_normalize_image, content)

    safe_prefix = re.sub(r"[^a-zA-Z0-9_-]", "-", prefix)[:80]
    filename = f"{safe_prefix}_{uuid.uuid4().hex}.jpg"
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    target = (UPLOAD_DIRECTORY / filename).resolve()
    if target.parent != UPLOAD_DIRECTORY:
        raise HTTPException(400, "非法文件名")
    await asyncio.to_thread(target.write_bytes, normalized)
    digest = hashlib.sha256(normalized).hexdigest()
    return SavedImage(
        filename=filename,
        path=str(target),
        url=f"/api/users/me/photos/files/{filename}",
        sha256=digest,
        quality=quality,
    )


def sha256_file(path: str | Path) -> str:
    """Return a stable content fingerprint without retaining image bytes."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_image_path(url_or_path: str | Path) -> Path:
    """Resolve legacy and authenticated photo URLs inside the upload directory."""
    candidate = (UPLOAD_DIRECTORY / Path(str(url_or_path)).name).resolve()
    if candidate.parent != UPLOAD_DIRECTORY or not candidate.is_file():
        raise FileNotFoundError("photo not found")
    return candidate


async def delete_saved_image(url_or_path: str | Path | None) -> None:
    if not url_or_path:
        return
    try:
        target = resolve_image_path(url_or_path)
    except FileNotFoundError:
        return
    await asyncio.to_thread(target.unlink, missing_ok=True)
