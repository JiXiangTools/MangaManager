import shutil
from pathlib import Path

from fastapi import UploadFile
from PIL import Image

from .config import Settings


IMAGE_FORMATS = {
    "jpg": ("JPEG", ".jpg"),
    "png": ("PNG", ".png"),
    "webp": ("WEBP", ".webp")
}


def ensure_data_dirs(settings: Settings) -> None:
    settings.library_dir.mkdir(parents=True, exist_ok=True)
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)


def image_extension(filename: str, content_type: str = "") -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"
    return ".jpg"


def image_size(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as img:
            return img.width, img.height
    except Exception:
        return 0, 0


async def save_upload(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


def convert_image(source: Path, destination: Path, image_format: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fmt, _suffix = IMAGE_FORMATS[image_format]
    try:
        with Image.open(source) as img:
            if fmt == "JPEG":
                img = img.convert("RGB")
            img.save(destination, format=fmt)
    except Exception:
        shutil.copyfile(source, destination)

