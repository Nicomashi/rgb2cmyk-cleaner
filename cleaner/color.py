"""ICC conversion only; no arithmetic RGB/CMYK approximation."""
from functools import lru_cache
from io import BytesIO
from PIL import Image, ImageCms

SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
SRGB_BYTES = SRGB.tobytes()

def profile(blob):
    return ImageCms.ImageCmsProfile(BytesIO(blob))

def description(blob):
    return ImageCms.getProfileDescription(profile(blob)).strip()

def validate_cmyk(blob):
    p = profile(blob)
    if p.profile.xcolor_space.strip() != 'CMYK':
        raise ValueError('Нужен выходной ICC-профиль CMYK.')
    return p

@lru_cache(maxsize=12)
def transform(src, dst, input_mode, output_mode):
    return ImageCms.buildTransformFromOpenProfiles(profile(src), profile(dst), input_mode,
        output_mode, renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
        flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)

def convert(image, source, target, output_mode):
    return ImageCms.applyTransform(image, transform(source, target, image.mode, output_mode))

def preview(image, icc):
    return convert(image, icc, SRGB_BYTES, 'RGB')
