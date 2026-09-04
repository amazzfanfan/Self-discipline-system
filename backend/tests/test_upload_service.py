import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from PIL import Image

from app.main import app
from app.services import upload_service


def make_upload(content: bytes, content_type: str, filename: str = "photo.jpg"):
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


def make_jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (256, 256), "#5b8def").save(output, format="JPEG")
    return output.getvalue()


def test_save_image_uses_verified_extension_and_generated_name(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_service, "UPLOAD_DIRECTORY", tmp_path.resolve())
    upload = make_upload(make_jpeg(), "image/jpeg", "attack.svg")

    saved = asyncio.run(upload_service.save_image_upload(upload, "user/avatar"))

    assert saved.filename.endswith(".jpg")
    assert "/" not in saved.filename
    assert len(saved.sha256) == 64
    assert (tmp_path / saved.filename).read_bytes().startswith(b"\xff\xd8\xff")
    assert saved.url.startswith("/api/users/me/photos/files/")


def test_save_image_rejects_spoofed_content(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_service, "UPLOAD_DIRECTORY", tmp_path.resolve())
    upload = make_upload(b"<script>alert(1)</script>", "image/png", "photo.png")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(upload_service.save_image_upload(upload, "user"))

    assert exc_info.value.status_code == 415


def test_save_image_rejects_unsupported_declared_type():
    upload = make_upload(b"GIF89a", "image/gif", "photo.gif")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(upload_service.save_image_upload(upload, "user"))

    assert exc_info.value.status_code == 415


def test_onboarding_upload_contract_excludes_full_body_photos():
    schema = app.openapi()
    request_schema = schema["paths"]["/api/users/me/photos/upload"]["post"][
        "requestBody"
    ]["content"]["multipart/form-data"]["schema"]
    component_name = request_schema["$ref"].rsplit("/", 1)[-1]
    properties = schema["components"]["schemas"][component_name]["properties"]

    assert set(properties) == {"avatar", "portrait_photo"}
