"""Lazy source loading. Only preview pixels or a bounded strip enter Python."""
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
import hashlib
import re
import numpy as np
import pymupdf
import pyvips
import tifffile
from PIL import Image
from .color import SRGB_BYTES, convert

pyvips.cache_set_max_mem(64*1024*1024)
pyvips.cache_set_max(0)
PDF_LOCK=Lock()

@dataclass(frozen=True)
class Raster:
    path: Path
    width: int
    height: int
    mode: str
    icc: bytes | None
    dpi: tuple[float,float]
    invert: bool=False
    alpha: bool=False

    def open(self):
        image=pyvips.Image.new_from_file(str(self.path),access='sequential')
        if self.invert: image=255-image
        if self.alpha: image=image.flatten(background=[0]*4 if self.mode=='CMYK' else [255])
        return image.cast('uchar')

    def cmyk(self,image,target):
        if self.mode=='CMYK':
            return image if self.icc==target else convert(image,self.icc,target,'CMYK')
        if self.mode=='L': image=image.convert('RGB')
        return convert(image,self.icc or SRGB_BYTES,target,'CMYK')

    def thumbnail(self,max_side=2400):
        image=self.open()
        scale=min(1,max_side/self.width,max_side/self.height)
        if scale<1: image=image.resize(scale)
        return Image.frombytes(self.mode,(image.width,image.height),image.write_to_memory())

    def save_preview(self,path,max_side=2400):
        image=self.thumbnail(max_side)
        image.save(path,format='TIFF',compression='tiff_lzw',icc_profile=self.icc,dpi=self.dpi)

    def preview(self,target,max_side=2400):
        pil=self.thumbnail(max_side)
        image=pil
        notes=[]
        if (image.width,image.height)!=(self.width,self.height):
            notes.append(f'Превью {image.width} × {image.height} px; полный экспорт {self.width} × {self.height} px.')
        if self.alpha: notes.append('Прозрачность сведена на белый фон.')
        if not self.icc: notes.append('Исходный ICC отсутствует: принят sRGB.')
        return self.cmyk(pil,target),notes

    def strips(self,target,rows=64):
        image=self.open()
        region=pyvips.Region.new(image)
        for y in range(0,self.height,rows):
            h=min(rows,self.height-y)
            pil=Image.frombytes(self.mode,(self.width,h),region.fetch(0,y,self.width,h))
            yield y,np.asarray(self.cmyk(pil,target)).copy()

def inspect_raster(path):
    path=Path(path)
    image=pyvips.Image.new_from_file(str(path),access='sequential')
    if image.format!='uchar': raise ValueError('16-битные и другие форматы глубины пока не поддерживаются; нужны 8 бит.')
    if image.get_typeof('n-pages') and image.get('n-pages')!=1:
        raise ValueError('Пока поддерживаются только одностраничные изображения.')
    if image.width*image.height>1_500_000_000 or image.width>200_000:
        raise ValueError('Предел этой версии: 1.5 Гп и 200000 px по ширине.')
    mode={'cmyk':'CMYK','srgb':'RGB','rgb':'RGB','b-w':'L'}.get(image.interpretation)
    if mode is None: raise ValueError('Нужен RGB, CMYK или серый растр.')
    alpha=bool(image.hasalpha())
    expected={'CMYK':4,'RGB':3,'L':1}[mode]+int(alpha)
    if image.bands!=expected: raise ValueError('Неподдерживаемое количество каналов.')
    icc=bytes(image.get('icc-profile-data')) if image.get_typeof('icc-profile-data') else None
    if mode=='CMYK' and not icc: raise ValueError('У CMYK-файла нет ICC. Сначала назначьте исходный профиль.')
    if mode=='L' and icc: raise ValueError('Gray ICC пока не поддерживается. Подготовьте RGB-файл.')
    dpi=(image.xres*25.4,image.yres*25.4)
    if image.get('vips-loader').startswith('tiff'):
        with tifffile.TiffFile(path) as tif:
            tags=tif.pages[0].tags
            unit=tags.get('ResolutionUnit')
            if unit and unit.value in (2,3) and 'XResolution' in tags and 'YResolution' in tags:
                factor=2.54 if unit.value==3 else 1
                dpi=tuple(tags[k].value[0]/tags[k].value[1]*factor for k in ('XResolution','YResolution'))
    return Raster(path,image.width,image.height,mode,icc,dpi,alpha=alpha)

def inspected_pdf(path,cache):
    """Only the inspected single-raster PDF layout; no general PDF rasterization."""
    path=Path(path); cache=Path(cache); cache.mkdir(parents=True,exist_ok=True)
    with PDF_LOCK, pymupdf.open(path) as doc:
        if len(doc)!=1: raise ValueError('Нужен одностраничный PDF.')
        page=doc[0]; images=page.get_images(full=True)
        if len(images)!=1 or images[0][8]!='DCTDecode' or images[0][5]!='DeviceCMYK':
            raise ValueError('PDF не соответствует проверенному CMYK JPEG-сценарию.')
        xref=images[0][0]
        obj=doc.xref_object(xref)
        if '/Decode [' in obj or images[0][1]: raise ValueError('Неподдерживаемый Decode или маска PDF.')
        match=re.search(r'/DefaultCMYK\s+(\d+)\s+0\s+R',doc.xref_object(page.xref))
        if not match: raise ValueError('Нет DefaultCMYK ICC в PDF.')
        iccref=re.search(r'/ICCBased\s+(\d+)\s+0\s+R',doc.xref_object(int(match[1])))
        if not iccref: raise ValueError('Не найден ICC PDF.')
        icc=doc.xref_stream(int(iccref[1]))
        fingerprint=f'{path.resolve()}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
        dest=cache/(hashlib.sha256(fingerprint.encode()).hexdigest()+'.jpg')
        if not dest.exists():
            part=dest.with_suffix('.part'); part.write_bytes(doc.xref_stream_raw(xref)); part.replace(dest)
        width,height=images[0][2:4]
        # libvips, like Pillow, normalizes Adobe JPEG inversion. These PDFs have
        # no /Decode array, so undo normalization to recover actual PDF inks.
        return Raster(dest,width,height,'CMYK',icc,
                      (width*72/page.rect.width,height*72/page.rect.height),invert=True)
