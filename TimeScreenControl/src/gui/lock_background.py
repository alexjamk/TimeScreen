"""Validated, shared lock-screen background image."""

import os
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from config.paths import LOCK_BACKGROUND_PATH


MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_OUTPUT_SIZE = (7680, 4320)


def install_background(source: Path, destination: Path = LOCK_BACKGROUND_PATH) -> None:
    """Decode and re-encode an administrator-selected image into ProgramData."""
    source = Path(source)
    if not source.is_file() or source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Выберите изображение размером не более 20 МБ")
    temp_path = None
    try:
        with Image.open(source) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Слишком большое изображение (более 40 млн пикселей)")
            image = ImageOps.exif_transpose(image)
            image.thumbnail(MAX_OUTPUT_SIZE, Image.Resampling.LANCZOS)
            image = image.convert("RGB")
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix="lock_background.", suffix=".tmp", dir=str(destination.parent))
            temp_path = Path(name)
            with os.fdopen(descriptor, "wb") as stream:
                image.save(stream, format="JPEG", quality=88, optimize=True)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(temp_path, destination)
    except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("Файл не является допустимым изображением") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def background_photo(master, width: int, height: int, path: Path = LOCK_BACKGROUND_PATH):
    """Return a Tk photo cropped to cover one monitor, or None on image failure."""
    if width <= 0 or height <= 0 or not path.is_file():
        return None
    try:
        with Image.open(path) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                return None
            fitted = ImageOps.fit(image.convert("RGB"), (width, height), Image.Resampling.LANCZOS)
            from PIL import ImageTk
            return ImageTk.PhotoImage(fitted, master=master)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
