# ads/signals.py
import os
import io
from PIL import Image, UnidentifiedImageError
import piexif
from django.conf import settings
from .models import AdvertisementImage


def convert_image_to_webp(ad_image_id, quality=85, target_kb=None, max_dim=None, min_quality=20):
    """
    Converts an AdvertisementImage to WebP.
    Handles JPEG/PNG safely and preserves EXIF only where applicable.
    """
    ad_image = AdvertisementImage.objects.get(id=ad_image_id)
    input_path = ad_image.image.path
    output_path = os.path.splitext(input_path)[0] + ".webp"

    # --- Open image ---
    try:
        img = Image.open(input_path)
        img_format = img.format or ""
    except (UnidentifiedImageError, Exception):
        return

    # --- Extract EXIF only for JPEG/TIFF ---
    exif_bytes = None
    if img_format.upper() in ("JPEG", "JPG", "TIFF"):
        try:
            exif_dict = piexif.load(input_path)
            exif_bytes = piexif.dump(exif_dict)
        except Exception:
            exif_bytes = img.info.get("exif")

    # --- Normalize image mode ---
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "transparency" in img.info or img.mode == "P" else "RGB")

    # --- Resize if needed ---
    if max_dim:
        w, h = img.size
        if max(w, h) > max_dim:
            ratio = max_dim / float(max(w, h))
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    # --- Save to WebP ---
    bio = io.BytesIO()
    save_kwargs = {
        "format": "WEBP",
        "quality": quality,
        "method": 6,
    }
    if exif_bytes:
        save_kwargs["exif"] = exif_bytes

    img.save(bio, **save_kwargs)
    with open(output_path, "wb") as f:
        f.write(bio.getvalue())

    # --- Update model safely ---
    ad_image.image.name = os.path.relpath(output_path, ad_image.image.storage.location)
    ad_image.is_converted = True
    ad_image.save(update_fields=["image", "is_converted"])

    # --- Delete original file ---
    if os.path.exists(input_path) and input_path != output_path:
        os.remove(input_path)


# import os
# import io
# import threading
# from PIL import Image, UnidentifiedImageError
# import piexif
# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from .models import AdvertisementImage

# def convert_image_to_webp(ad_image_id, quality=85, target_kb=None, max_dim=None, min_quality=20):
#     """
#     Converts an AdvertisementImage to WebP asynchronously.
#     Runs in a separate thread to avoid blocking requests.
#     """
#     try:
#         ad_image = AdvertisementImage.objects.get(id=ad_image_id)
#         input_path = ad_image.image.path
#         output_path = os.path.splitext(input_path)[0] + '.webp'

#         # --- Open image ---
#         try:
#             img = Image.open(input_path)
#         except UnidentifiedImageError:
#             return
#         except Exception:
#             return

#         # --- Extract EXIF ---
#         try:
#             exif_bytes = piexif.dump(piexif.load(input_path))
#         except Exception:
#             exif_bytes = img.info.get('exif')

#         # --- Normalize image mode ---
#         if img.mode not in ('RGB', 'RGBA'):
#             if 'transparency' in img.info or img.mode == 'P':
#                 img = img.convert('RGBA')
#             else:
#                 img = img.convert('RGB')

#         # --- Resize if needed ---
#         if max_dim:
#             w, h = img.size
#             if max(w, h) > max_dim:
#                 ratio = max_dim / float(max(w, h))
#                 img = img.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)

#         # --- Save WebP with target KB if specified ---
#         bio = io.BytesIO()
#         chosen_data = None

#         if target_kb:
#             target_bytes = int(target_kb) * 1024
#             q = quality
#             best_data, best_bytes = None, None
#             while q >= min_quality:
#                 bio.seek(0)
#                 img.save(bio, format='WEBP', quality=q, method=6, exif=exif_bytes)
#                 data = bio.getvalue()
#                 size = len(data)
#                 if best_bytes is None or size < best_bytes:
#                     best_bytes, best_data = size, data
#                 if size <= target_bytes:
#                     chosen_data = data
#                     break
#                 q -= 5
#             if chosen_data is None:
#                 chosen_data = best_data
#         else:
#             save_kwargs = {
#                 'format': 'WEBP',
#                 'quality': quality,
#                 'method': 6
#             }

#             if exif_bytes:
#                 save_kwargs['exif'] = exif_bytes

#             img.save(bio, **save_kwargs)
#             chosen_data = bio.getvalue()

#         # --- Write WebP file ---
#         with open(output_path, 'wb') as f:
#             f.write(chosen_data)

#         # --- Update model ---
#         ad_image.image.name = os.path.relpath(output_path, ad_image.image.storage.location)
#         ad_image.save(update_fields=['image'])

#         # Optional: delete original file if different
#         if os.path.exists(input_path) and input_path != output_path:
#             os.remove(input_path)

#     except AdvertisementImage.DoesNotExist:
#         return
