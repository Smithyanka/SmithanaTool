from __future__ import annotations
from typing import Iterable, List, Tuple
import os
from PIL import Image

# We exclude PSD/PSB explicitly
PSD_EXTS = {".psd", ".psb"}

def is_psd(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in PSD_EXTS

def filter_non_psd(paths: Iterable[str]) -> List[str]:
    """Return all paths except PSD/PSB; directories are ignored by caller."""
    out: List[str] = []
    for p in paths:
        try:
            if not is_psd(p):
                out.append(p)
        except Exception:
            # Ignore path errors quietly
            pass
    return out

def _ensure_png_mode(im: Image.Image) -> Image.Image:
    """
    Convert image to a PNG-suitable mode while keeping alpha if present.
    Avoids errors on exotic modes/profiles.
    """
    try:
        bands = im.getbands()
        has_alpha = "A" in bands
        if im.mode in ("P", "PA", "CMYK", "YCbCr") or (im.mode not in ("RGB","RGBA","L","LA")):
            im = im.convert("RGBA" if has_alpha else "RGB")
    except Exception:
        # Last resort, try lossless-ish conversion
        try:
            im = im.convert("RGBA")
        except Exception:
            pass
    return im

def convert_any_to_png(
    src_path: str,
    dst_path: str,
    png_compress_level: int = 6,
    optimize: bool = False,
    strip_metadata: bool = True,
) -> Tuple[bool, str]:
    """
    Try to convert *any* non-PSD file that Pillow can read into PNG.
    Returns (True, dst_path) on success or (False, error_message) on failure.
    """
    try:
        # PSD are explicitly unsupported here
        if is_psd(src_path):
            return False, "PSD/PSB: используйте отдельный конвертор PSD → PNG"
        if not os.path.exists(src_path):
            return False, f"Файл не найден: {src_path}"

        # Open the image via Pillow; load() to realize data then copy() to detach
        with Image.open(src_path) as _im:
            _im.load()
            im = _im.copy()

        # Some formats (animated GIF/WEBP/TIFF) will give first frame by default
        im = _ensure_png_mode(im)

        params = dict(
            compress_level=int(max(0, min(9, png_compress_level))),
        )
        if optimize:
            params["optimize"] = True

        # Strip metadata if requested
        if strip_metadata:
            exif = im.info.get("exif")
            if exif:
                # drop EXIF by not passing it further
                pass
        else:
            exif = im.info.get("exif")
            if exif:
                params["exif"] = exif  # type: ignore

        # Ensure folder exists
        os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)

        # Final guard
        if im.mode not in ("RGB", "RGBA", "L", "LA"):
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")

        im.save(dst_path, format="PNG", **params)
        return True, dst_path
    except Exception as e:
        return False, str(e)
