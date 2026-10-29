"""Bounded strip processing and atomic, profile-tagged TIFF output."""
from dataclasses import asdict
from pathlib import Path
import json
import time
import zlib
import numpy as np
import tifffile
from .engine import clean_u8
from .color import description

class Cancelled(Exception): pass

def export_full(source,target,settings,destination,progress=lambda p:None,cancelled=lambda:False,rows=64):
    destination=Path(destination)
    part=destination.with_suffix('.part.tif')
    report=destination.with_suffix('.json')
    report_part=report.with_suffix('.json.part')
    start=time.perf_counter(); count=0; changed=0; removed=0.; tac_before=0.; tac_after=0.; tac_exceeded=0; k_exceeded=0
    # Reserve classic-TIFF headroom. Strip offsets remain 64-bit for large rasters.
    bigtiff=source.width*source.height*4>3_500_000_000
    def strips():
        nonlocal count,changed,removed,tac_before,tac_after,tac_exceeded,k_exceeded
        for y,before in source.strips(target,rows):
            if cancelled(): raise Cancelled('Экспорт отменён')
            after=clean_u8(before,settings)
            b=before.astype(np.int16); a=after.astype(np.int16)
            tb=b.sum(axis=-1)*100/255; ta=a.sum(axis=-1)*100/255
            count+=before.shape[0]*source.width
            changed+=int(np.count_nonzero(np.any(before!=after,axis=-1)))
            removed+=float((b[...,:3]-a[...,:3]).sum())*100/255
            tac_before=max(tac_before,float(tb.max())); tac_after=max(tac_after,float(ta.max()))
            tac_exceeded+=int(np.count_nonzero(ta>settings.tac+.01))
            k_exceeded+=int(np.count_nonzero(a[...,3]*100/255>settings.max_k+.01))
            yield zlib.compress(after.tobytes(),level=3)
            progress(round((y+before.shape[0])/source.height*99,1))
    try:
        with tifffile.TiffWriter(part,bigtiff=bigtiff) as writer:
            writer.write(strips(),shape=(source.height,source.width,4),dtype=np.uint8,
                         photometric='separated',planarconfig='contig',rowsperstrip=rows,
                         compression='deflate',iccprofile=target,resolution=source.dpi,
                         resolutionunit='INCH',metadata=None,software='RGB2CMYK Cleaner')
        if cancelled(): raise Cancelled('Экспорт отменён')
        with tifffile.TiffFile(part) as check:
            page=check.pages[0]
            assert (page.imagewidth,page.imagelength)==(source.width,source.height)
            assert page.tags[34675].value==target
            assert page.photometric==5
        info={'size':[source.width,source.height],'dpi':source.dpi,'bigtiff':bigtiff,
              'profile':description(target),'settings':asdict(settings),'seconds':round(time.perf_counter()-start,2),
              'stats':{'changed_pct':round(changed/count*100,2),'removed_mean':round(removed/count,2),
                       'tac_before':round(tac_before,1),'tac_after':round(tac_after,1),
                       'tac_exceeded_pct':round(tac_exceeded/count*100,6),'k_exceeded_pct':round(k_exceeded/count*100,6),
                       'tac_exceeded_pixels':tac_exceeded,'k_exceeded_pixels':k_exceeded}}
        report_part.write_text(json.dumps(info,ensure_ascii=False,indent=2))
        part.replace(destination); report_part.replace(report)
        progress(100)
        return info
    except BaseException:
        part.unlink(missing_ok=True); report_part.unlink(missing_ok=True)
        raise
