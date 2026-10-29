from collections import OrderedDict
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from threading import Lock, RLock, Event
from contextlib import asynccontextmanager
import shutil
from concurrent.futures import ThreadPoolExecutor
import base64
import json
import time
import uuid
from typing import Literal
import numpy as np
import pyvips
from fastapi import FastAPI, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from PIL import Image
from cleaner.engine import Settings, clean_u8, statistics
from cleaner.color import preview, description, validate_cmyk, SRGB_BYTES, convert
from cleaner.io import tiff_bytes
from cleaner.raster import inspect_raster
from cleaner.full_export import export_full, Cancelled
from starlette.concurrency import run_in_threadpool

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'.runtime'
UPLOADS=RUNTIME/'uploads'
PROFILE=ROOT/'profiles'/'source-fogra39.icc'
@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(reset_workspace)
    try:
        yield
    finally:
        await run_in_threadpool(reset_workspace)

app=FastAPI(title='RGB2CMYK Cleaner • Prototype',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

@app.middleware('http')
async def no_browser_cache(request,call_next):
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    return response
work_lock=RLock(); workspace_id=uuid.uuid4().hex
lock=Lock(); results=OrderedDict(); sources={}; profiles={}; source_previews={}; source_notes={}
jobs=OrderedDict(); executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix="full-export")
FULL_OUTPUT=RUNTIME/'exports'
futures={}
page_tickets=OrderedDict(); page_sequence=0; active_sequence=0

def require_workspace(request):
    if request.headers.get('X-Workspace')!=workspace_id:
        raise HTTPException(409,'Страница устарела. Перезагрузите её и откройте файл заново.')

def clear_materials():
    """Caller holds work_lock. Stop writers before removing their working files."""
    with lock:
        for job in jobs.values(): job['cancel'].set()
        running=list(futures.values())
    for future in running:
        future.result()
    with lock:
        results.clear(); sources.clear(); source_previews.clear(); source_notes.clear()
        jobs.clear(); futures.clear()
    # Disable libvips' operation cache so removed files are not retained by readers.
    pyvips.cache_set_max(0)
    for folder in (UPLOADS,FULL_OUTPUT):
        if folder.exists(): shutil.rmtree(folder)
    if RUNTIME.exists() and not any(RUNTIME.iterdir()): RUNTIME.rmdir()

def reset_workspace():
    global workspace_id
    with work_lock:
        clear_materials()
        profiles.clear()
        workspace_id=uuid.uuid4().hex
        return workspace_id


class Controls(BaseModel):
    strength: float=Field(1,ge=0,le=1,allow_inf_nan=False)
    compensation: float=Field(.82,ge=0,le=2,allow_inf_nan=False)
    max_k: float=Field(100,ge=0,le=100,allow_inf_nan=False)
    neutral_protection: float=Field(1,ge=0,le=1,allow_inf_nan=False)
    tac: float=Field(300,ge=0,le=400,allow_inf_nan=False)
    smooth_ties: bool=True

class Process(BaseModel):
    source: str
    profile: str='source'
    settings: Controls=Controls()
    channel: str='color'
    before_mode: Literal['source','cmyk']='source'

@app.get('/')
def index():
    global page_sequence
    with work_lock:
        # Serving HTML (including health checks/prefetch) must not clear an active file.
        identifier=uuid.uuid4().hex
        page_sequence+=1; page_tickets[identifier]=page_sequence
        while len(page_tickets)>128: page_tickets.popitem(last=False)
        html=(ROOT/'static'/'index.html').read_text().replace('__WORKSPACE_ID__',identifier)
        return HTMLResponse(html,headers={'Cache-Control':'no-store'})

@app.post('/api/workspace/open')
def open_workspace(request:Request):
    global workspace_id,active_sequence
    identifier=request.headers.get('X-Workspace')
    with work_lock:
        sequence=page_tickets.pop(identifier,None)
        if sequence is None or sequence<active_sequence:
            raise HTTPException(409,'Обновите страницу для новой рабочей сессии.')
        reset_workspace()
        workspace_id=identifier;active_sequence=sequence
        return {'ready':True}

@app.post('/api/workspace/{identifier}/close')
def close_workspace(identifier:str):
    with work_lock:
        # A late unload beacon from the old document must not clear a newer one.
        if identifier==workspace_id: reset_workspace()
    return Response(status_code=204)


@app.get('/api/catalog')
def catalog():
    if not PROFILE.exists(): raise HTTPException(503,'Отсутствует рабочий CMYK ICC в profiles/source-fogra39.icc.')
    return {'samples':[],'profile':description(PROFILE.read_bytes()),'defaults':asdict(Settings())}

@app.post('/api/materials/clear')
def discard_materials(request:Request):
    with work_lock:
        require_workspace(request)
        clear_materials()
    return Response(status_code=204)

def source_path(key):
    with lock: path=sources.get(key)
    if path is None: raise HTTPException(404,'Файл не найден. Откройте его заново.')
    return path

def profile_bytes(key):
    if key=='source': return PROFILE.read_bytes()
    with lock: blob=profiles.get(key)
    if blob is None: raise HTTPException(404,'Профиль не найден.')
    return blob

def png_data(image):
    # Keep sample pixels intact so the 100% view and eyedropper agree.
    buf=BytesIO(); image.save(buf,format='PNG',compress_level=3,icc_profile=SRGB_BYTES if image.mode=='RGB' else None)
    return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()

def channel_image(array,channel,icc,before=None):
    if channel=='color': return preview(Image.fromarray(array,'CMYK'),icc)
    if channel=='map':
        amount=np.maximum(0,before[...,:3].astype(float)-array[...,:3]).sum(axis=-1)/255
        # White unchanged; green = 100 percentage points removed.
        white=np.ones((*amount.shape,3))*255
        return Image.fromarray(np.uint8(white*(1-amount[...,None])+np.array([45,189,140])*amount[...,None]))
    return Image.fromarray(255-array[...,'CMYK'.index(channel)],'L')

@app.post('/api/process')
def process(req:Process,request:Request):
    with work_lock:
        require_workspace(request)
        return process_locked(req)

def process_locked(req):
    if req.channel not in ('color','map','C','M','Y','K'): raise HTTPException(422,'Неизвестный канал.')
    start=time.perf_counter()
    try:
        icc=profile_bytes(req.profile)
        raster=inspect_raster(source_path(req.source))
        original=source_previews[req.source]
        source_raster=raster
        img=raster.cmyk(original,icc)
        notes=source_notes.get(req.source,[])
        original_size=[raster.width,raster.height]
        before=np.asarray(img).copy()
        settings=Settings(**req.settings.model_dump())
        after=clean_u8(before,settings)
        token=uuid.uuid4().hex
        source_mode=original.mode
        source_icc=source_raster.icc or SRGB_BYTES
        comparison=req.before_mode if req.channel=='color' else 'cmyk'
        metadata={'pixels':np.asarray(original).copy(),'mode':source_mode}
        record=(before,after,icc,settings,req.source,metadata)
        with lock:
            results[token]=record
            while len(results)>2: results.popitem(last=False)
        first=channel_image(before,req.channel,icc,before)
        if comparison=='source':
            original_rgb=original.convert('RGB') if source_mode=='L' else original
            first=convert(original_rgb,source_icc,SRGB_BYTES,'RGB')
        left_label=f'Исходник · {source_mode}' if comparison=='source' else 'CMYK до очистки'
        right_label='CMYK после очистки'
        if req.channel=='map': left_label='Без очистки'; right_label='Удалённая краска'
        elif req.channel!='color':
            left_label=f'{req.channel} до очистки'; right_label=f'{req.channel} после очистки'
        last=channel_image(after,req.channel,icc,before)
        return {'id':token,'before':png_data(first),'after':png_data(last),
                'width':img.width,'height':img.height,'original_size':original_size,'notes':notes,
                'source_mode':source_mode,'comparison':comparison,'left_label':left_label,'right_label':right_label,
                'source_profile':description(source_icc) if source_raster.icc else 'sRGB',
                'stats':statistics(before,after,settings),'profile':description(icc),
                'seconds':round(time.perf_counter()-start,2)}
    except HTTPException: raise
    except (ValueError,OSError,Image.DecompressionBombError,pyvips.Error) as e: raise HTTPException(422,str(e)) from e

def result(token):
    with lock: r=results.get(token)
    if r is None: raise HTTPException(410,'Результат устарел. Нажмите «Пересчитать».')
    return r

@app.get('/api/pixel/{token}')
def pixel(token:str,x:int,y:int):
    b,a,_,_,_,meta=result(token)
    if not (0<=x<a.shape[1] and 0<=y<a.shape[0]): raise HTTPException(422,'За пределами изображения.')
    return {'x':x,'y':y,'before':np.round(b[y,x].astype(float)*100/255,1).tolist(),
            'after':np.round(a[y,x].astype(float)*100/255,1).tolist(),
            'source_mode':meta['mode'],'source_pixel':np.atleast_1d(meta['pixels'][y,x]).astype(int).tolist()}

class SamplePoint(BaseModel):
    x: int=Field(ge=0)
    y: int=Field(ge=0)

class SampleRequest(BaseModel):
    points: list[SamplePoint]=Field(min_length=1,max_length=33)
    area: Literal[1,3,5,11]=1

@app.post('/api/samples/{token}')
def samples(token:str,req:SampleRequest,request:Request):
    """Read original pixels, then apply the same pixel-local transform as export.

    Never sample the rescaled RGB screen preview. Average AFTER cleaning, not
    before the nonlinear transform. All points share one lazy source reader.
    """
    with work_lock:
        require_workspace(request)
        _,_,icc,settings,source,_=result(token)
        raster=original_raster(source)
        if any(p.x>=raster.width or p.y>=raster.height for p in req.points):
            raise HTTPException(422,'За пределами изображения.')
        image=pyvips.Image.new_from_file(str(raster.path),access='random')
        if raster.invert: image=255-image
        if raster.alpha: image=image.flatten(background=[0]*4 if raster.mode=='CMYK' else [255])
        region=pyvips.Region.new(image.cast('uchar'))
        output=[];radius=req.area//2
        for p in req.points:
            x0=max(0,p.x-radius); y0=max(0,p.y-radius)
            w=min(raster.width,p.x+radius+1)-x0;h=min(raster.height,p.y+radius+1)-y0
            original=Image.frombytes(raster.mode,(w,h),region.fetch(x0,y0,w,h))
            native=np.asarray(original)
            if native.ndim==2: native=native[...,None]
            before=np.asarray(raster.cmyk(original,icc))
            after=clean_u8(before,settings)
            rgb_original=original.convert('RGB') if raster.mode=='L' else original
            swatch_before=np.asarray(convert(rgb_original,raster.icc or SRGB_BYTES,SRGB_BYTES,'RGB'))
            swatch_cmyk_before=np.asarray(preview(Image.fromarray(before,'CMYK'),icc))
            swatch_after=np.asarray(preview(Image.fromarray(after,'CMYK'),icc))
            mean=lambda a:np.asarray(a,dtype=float).mean(axis=(0,1))
            output.append({'x':p.x,'y':p.y,'source_mode':raster.mode,
                'source':np.round(mean(native)*(100/255 if raster.mode=='CMYK' else 1),1).tolist(),
                'before':np.round(mean(before)*100/255,1).tolist(),
                'after':np.round(mean(after)*100/255,1).tolist(),
                'tac':round(float(mean(after).sum()*100/255),1),
                'swatch_before':np.rint(mean(swatch_before)).astype(int).tolist(),
                'swatch_cmyk_before':np.rint(mean(swatch_cmyk_before)).astype(int).tolist(),
                'swatch_after':np.rint(mean(swatch_after)).astype(int).tolist()})
        return {'points':output,'area':req.area,'basis':'original'}

@app.post('/api/demo')
def demo(request:Request):
    # An explicit user action, never an automatically restored working file.
    with (ROOT/'static'/'demo.jpg').open('rb') as f:
        return upload(UploadFile(file=f,filename='studio.jpg'),request)

@app.get('/api/export/{token}')
def export(token:str,kind:str='tiff'):
    before,after,icc,settings,source,_=result(token)
    img=Image.fromarray(after,'CMYK')
    name=f'cleaner-{source[:12]}'
    if kind=='tiff': data=tiff_bytes(img,icc); mime='image/tiff'; ext='tif'
    elif kind=='png':
        buf=BytesIO(); preview(img,icc).save(buf,format='PNG',icc_profile=SRGB_BYTES)
        data=buf.getvalue(); mime='image/png'; ext='png'
    elif kind=='report':
        data=json.dumps({'source':source,'settings':asdict(settings),'profile':description(icc),
          'size':img.size,'stats':statistics(before,after,settings)},ensure_ascii=False,indent=2).encode()
        mime='application/json'; ext='json'
    else: raise HTTPException(422,'Неизвестный формат.')
    return Response(data,media_type=mime,headers={'Content-Disposition':f'attachment; filename="{name}.{ext}"'})

@app.post('/api/upload')
def upload(file:UploadFile,request:Request):
    with work_lock:
        try:
            require_workspace(request)
            # Even an unsupported new file replaces the previous working material.
            clear_materials()
            suffix=Path(file.filename or '').suffix.lower()
            if suffix not in ('.png','.jpg','.jpeg','.tif','.tiff'):
                raise HTTPException(422,'Откройте PNG, JPEG или TIFF.')
            UPLOADS.mkdir(parents=True,exist_ok=True)
            key=uuid.uuid4().hex; path=UPLOADS/(key+suffix)
            total=0
            try:
                with path.open('wb') as destination:
                    while chunk:=file.file.read(1024*1024):
                        total+=len(chunk)
                        if total>4*1024**3: raise ValueError('Максимум 4 ГБ на файл.')
                        destination.write(chunk)
                raster=inspect_raster(path)
                original=raster.thumbnail()
                # Validate color conversion, but retain the unconverted preview in RAM.
                raster.cmyk(original,PROFILE.read_bytes())
                notes=[]
                if raster.alpha: notes.append('Прозрачность сведена на белый фон.')
                if not raster.icc: notes.append('Исходный ICC отсутствует: принят sRGB.')
            except Exception as e:
                clear_materials()
                raise HTTPException(422,str(e)) from e
            with lock:
                sources[key]=path; source_previews[key]=original; source_notes[key]=notes
            return {'id':key,'name':Path(file.filename).name,'size':original.size,
                    'original_size':[raster.width,raster.height],'notes':notes}
        finally:
            file.file.close()

@app.post('/api/profile')
def upload_profile(file:UploadFile,request:Request):
    with work_lock:
        try:
            require_workspace(request)
            return upload_profile_locked(file)
        finally:
            file.file.close()

def upload_profile_locked(file):
    blob=file.file.read(4*1024*1024+1)
    if len(blob)>4*1024*1024: raise HTTPException(413,'Максимум 4 МБ для ICC.')
    try: validate_cmyk(blob); name=description(blob)
    except Exception as e: raise HTTPException(422,'Не удалось открыть CMYK ICC: '+str(e)) from e
    key=uuid.uuid4().hex
    with lock: profiles[key]=blob
    return {'id':key,'name':name}


def original_raster(key):
    return inspect_raster(source_path(key))

def job_view(job):
    return {k:v for k,v in job.items() if k not in ('cancel','path')}

@app.post('/api/full-export/{token}')
def start_full_export(token:str,request:Request):
    with work_lock:
        require_workspace(request)
        return start_full_export_locked(token)

def start_full_export_locked(token):
    _,_,icc,settings,source,_=result(token)
    job_id=uuid.uuid4().hex
    cancel=Event()
    FULL_OUTPUT.mkdir(parents=True,exist_ok=True)
    path=FULL_OUTPUT/f'cleaner-{source[:12]}-{job_id[:8]}-full.tif'
    with lock:
        if any(j['status'] in ('queued','running','cancelling') for j in jobs.values()):
            raise HTTPException(409,'Полный экспорт уже выполняется. Дождитесь завершения или отмените его.')
        # Keep only the latest export, never accumulate full-size files.
        for old in jobs.values():
            old['path'].unlink(missing_ok=True)
            old['path'].with_suffix('.json').unlink(missing_ok=True)
        jobs.clear(); futures.clear()
        jobs[job_id]={'id':job_id,'status':'queued','progress':0,'cancel':cancel,'path':path,
                      'source':source,'settings':asdict(settings),'profile':description(icc)}
        while len(jobs)>20: jobs.popitem(last=False)
    def update(**values):
        with lock: jobs[job_id].update(values)
    def run():
        try:
            if cancel.is_set(): raise Cancelled()
            update(status='running')
            raster=original_raster(source)
            update(size=[raster.width,raster.height])
            info=export_full(raster,icc,settings,path,
                             progress=lambda p:update(progress=p),cancelled=cancel.is_set)
            update(status='complete',progress=100,report=info,
                   download=f'/api/full-export/{job_id}/file',report_url=f'/api/full-export/{job_id}/report')
        except Cancelled:
            update(status='cancelled')
        except Exception as e:
            update(status='failed',error=str(e))
    future=executor.submit(run)
    with lock: futures[job_id]=future
    with lock: return job_view(jobs[job_id])

@app.get('/api/full-export/{job_id}')
def full_status(job_id:str):
    with lock:
        if job_id not in jobs: raise HTTPException(404,'Задание не найдено.')
        return job_view(jobs[job_id])

@app.post('/api/full-export/{job_id}/cancel')
def cancel_full_export(job_id:str):
    with lock:
        job=jobs.get(job_id)
        if job is None: raise HTTPException(404,'Задание не найдено.')
        if job['status'] in ('queued','running','cancelling'):
            job['cancel'].set(); job['status']='cancelling'
        return job_view(job)

@app.get('/api/full-export/{job_id}/file')
def full_file(job_id:str):
    with lock: job=jobs.get(job_id)
    if job is None: raise HTTPException(404,'Задание не найдено.')
    if job['status']!='complete': raise HTTPException(409,'Файл ещё не готов.')
    return FileResponse(job['path'],media_type='image/tiff',filename=job['path'].name)

@app.get('/api/full-export/{job_id}/report')
def full_report(job_id:str):
    with lock: job=jobs.get(job_id)
    if job is None: raise HTTPException(404,'Задание не найдено.')
    if job['status']!='complete': raise HTTPException(409,'Отчёт ещё не готов.')
    return FileResponse(job['path'].with_suffix('.json'),media_type='application/json',filename=job['path'].stem+'.json')
