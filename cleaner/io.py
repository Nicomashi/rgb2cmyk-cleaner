from io import BytesIO
from pathlib import Path
from PIL import Image
from .color import SRGB_BYTES, convert, validate_cmyk

MAX_PIXELS = 25_000_000
MAX_SIDE = 2400

def load_image(path: Path, target: bytes):
    validate_cmyk(target)
    with Image.open(path) as image:
        if image.width*image.height>MAX_PIXELS:
            raise ValueError('Для прототипа максимум 25 Мп. Сначала уменьшите изображение.')
        if image.format=='PNG':
            with path.open('rb') as stream:
                header=stream.read(25)
            if len(header)==25 and header[24]>8:
                raise ValueError('16-битные PNG пока не поддерживаются.')
        if image.n_frames != 1:
            raise ValueError('Пока поддерживаются только одностраничные изображения.')
        if image.mode not in ('CMYK','RGB','RGBA','L','LA','P'):
            raise ValueError('Прототип поддерживает только 8-битные RGB/CMYK изображения.')
        if hasattr(image,'tag_v2') and any(b!=8 for b in image.tag_v2.get(258, (8,))):
            raise ValueError('16-битные TIFF пока не поддерживаются.')
        embedded=image.info.get('icc_profile')
        original_size=image.size
        image.thumbnail((MAX_SIDE,MAX_SIDE),Image.Resampling.LANCZOS)
        mode=image.mode
        notes=[]
        if original_size!=image.size: notes.append(f'Уменьшено до {image.width} × {image.height} px.')
        if mode=='CMYK':
            if not embedded: raise ValueError('У CMYK-файла нет ICC. Сначала назначьте исходный профиль.')
            result=image.copy() if embedded==target else convert(image,embedded,target,'CMYK')
        else:
            if mode in ('RGBA','LA','P'):
                rgba=image.convert('RGBA')
                base=Image.new('RGB',rgba.size,'white'); base.paste(rgba,mask=rgba.getchannel('A'))
                image=base
                notes.append('Прозрачность сведена на белый фон.')
            elif mode=='L':
                if embedded: raise ValueError('Gray ICC пока не поддерживается. Подготовьте RGB-файл.')
                image=image.convert('RGB')
            if not embedded: notes.append('Исходный ICC отсутствует: принят sRGB.')
            result=convert(image,embedded or SRGB_BYTES,target,'CMYK')
        return result, notes

def tiff_bytes(image, icc):
    buf=BytesIO()
    image.save(buf,format='TIFF',compression='tiff_lzw',icc_profile=icc,dpi=(150,150))
    return buf.getvalue()
