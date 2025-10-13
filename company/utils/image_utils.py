# vendors/utils/image_utils.py
import io
import os
from PIL import Image, UnidentifiedImageError
import piexif
from django.core.files.base import ContentFile

def convert_to_webp_file(img_file, quality=85, target_kb=None, max_dim=None, min_quality=20):
    """
    Converts an uploaded image to WebP synchronously.
    Returns a Django ContentFile ready to be saved to ImageField.
    """

    # --- Open image ---
    try:
        img = Image.open(img_file)
    except UnidentifiedImageError:
        raise ValueError("Invalid image file")
    
    # --- Extract EXIF ---
    try:
        exif_bytes = piexif.dump(piexif.load(img_file))
    except Exception:
        exif_bytes = img.info.get('exif')

    # --- Normalize image mode ---
    if img.mode not in ('RGB', 'RGBA'):
        if 'transparency' in img.info or img.mode == 'P':
            img = img.convert('RGBA')
        else:
            img = img.convert('RGB')

    # --- Resize if max_dim provided ---
    if max_dim:
        w, h = img.size
        if max(w, h) > max_dim:
            ratio = max_dim / float(max(w, h))
            img = img.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)

    # --- Convert to WebP ---
    bio = io.BytesIO()
    chosen_data = None

    if target_kb:
        target_bytes = int(target_kb) * 1024
        q = quality
        best_data, best_bytes = None, None
        while q >= min_quality:
            bio.seek(0)
            save_kwargs = {'format': 'WEBP', 'quality': q, 'method': 6}
            if exif_bytes:
                save_kwargs['exif'] = exif_bytes
            img.save(bio, **save_kwargs)
            data = bio.getvalue()
            size = len(data)
            if best_bytes is None or size < best_bytes:
                best_bytes, best_data = size, data
            if size <= target_bytes:
                chosen_data = data
                break
            q -= 5
        if chosen_data is None:
            chosen_data = best_data
    else:
        save_kwargs = {'format': 'WEBP', 'quality': quality, 'method': 6}
        if exif_bytes:
            save_kwargs['exif'] = exif_bytes
        img.save(bio, **save_kwargs)
        chosen_data = bio.getvalue()

    # --- Return Django-compatible file ---
    bio.seek(0)
    return ContentFile(chosen_data, name=os.path.splitext(img_file.name)[0] + '.webp')
