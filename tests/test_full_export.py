import io
import time
from pathlib import Path
import numpy as np
import pytest
import tifffile
from PIL import Image
from fastapi.testclient import TestClient
from app import app,ROOT,workspace_id
from cleaner.color import SRGB_BYTES,convert
from cleaner.engine import Settings,clean_u8
from cleaner.raster import inspect_raster
from cleaner.full_export import export_full,Cancelled

ICC=(ROOT/'profiles/source-fogra39.icc').read_bytes()

def test_stream_matches_engine_across_strip_boundaries(tmp_path):
    src=np.random.default_rng(4).integers(0,256,(173,777,4),dtype=np.uint8)
    path=tmp_path/'original.tif'
    Image.fromarray(src,'CMYK').save(path,icc_profile=ICC,dpi=(144,288))
    out=tmp_path/'result.tif'; progress=[]
    export_full(inspect_raster(path),ICC,Settings(),out,progress.append,rows=32)
    with tifffile.TiffFile(out) as t:
        np.testing.assert_array_equal(t.asarray(),clean_u8(src,Settings()))
        assert t.pages[0].tags[34675].value==ICC
        assert t.pages[0].tags['XResolution'].value==(144,1)
        assert t.pages[0].tags['YResolution'].value==(288,1)
    assert progress[-1]==100
    assert progress==sorted(progress)
    assert not list(tmp_path.glob('*.part*'))

def test_zero_strength_preserves_full_source_pixels(tmp_path):
    src=np.random.default_rng(6).integers(0,256,(69,171,4),dtype=np.uint8)
    path=tmp_path/'source.tif'; Image.fromarray(src,'CMYK').save(path,icc_profile=ICC)
    out=tmp_path/'out.tif'
    export_full(inspect_raster(path),ICC,Settings(strength=0),out)
    np.testing.assert_array_equal(tifffile.imread(out),src)

def test_cancel_removes_partial_output(tmp_path):
    path=tmp_path/'source.tif'
    Image.new('CMYK',(100,200),(100,90,20,10)).save(path,icc_profile=ICC)
    cancelled=[False]
    def progress(p): cancelled[0]=True
    out=tmp_path/'cancelled.tif'
    with pytest.raises(Cancelled):
        export_full(inspect_raster(path),ICC,Settings(),out,progress,lambda:cancelled[0],rows=16)
    assert not out.exists()
    assert not list(tmp_path.glob('*.part*'))
    assert not out.with_suffix('.json').exists()

def test_failure_removes_partial_output(tmp_path):
    path=tmp_path/'source.tif'
    Image.new('CMYK',(50,50)).save(path,icc_profile=ICC)
    def failure(p): raise RuntimeError('disk/job failure')
    out=tmp_path/'failed.tif'
    with pytest.raises(RuntimeError): export_full(inspect_raster(path),ICC,Settings(),out,failure,rows=16)
    assert not out.exists()
    assert not list(tmp_path.glob('*.part*'))

def test_original_export_is_not_enlarged_preview(tmp_path,monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module,'FULL_OUTPUT',tmp_path)
    client=TestClient(app,headers={"X-Workspace":workspace_id})
    rgb=np.random.default_rng(12).integers(0,256,(59,3201,3),dtype=np.uint8)
    buf=io.BytesIO();Image.fromarray(rgb).save(buf,format='PNG',icc_profile=SRGB_BYTES)
    upload=client.post('/api/upload',files={'file':('original.png',buf.getvalue(),'image/png')})
    assert upload.status_code==200,upload.text
    source=upload.json()['id']
    assert upload.json()['original_size']==[3201,59]
    preview=client.post('/api/process',json={'source':source,'settings':{'compensation':.5}}).json()
    assert preview['width']==2400
    assert preview['original_size']==[3201,59]
    start=client.post('/api/full-export/'+preview['id'])
    assert start.status_code==200,start.text
    job=start.json()['id']
    # Subsequent UI settings must not affect the captured export settings.
    client.post('/api/process',json={'source':source,'settings':{'strength':0}})
    for _ in range(200):
        state=client.get('/api/full-export/'+job).json()
        if state['status'] not in ('queued','running'): break
        time.sleep(.01)
    assert state['status']=='complete',state
    assert state['settings']['compensation']==.5
    assert state['report']['size']==[3201,59]
    response=client.get(state['download']);assert response.status_code==200
    with tifffile.TiffFile(io.BytesIO(response.content)) as tif:
        original=convert(Image.fromarray(rgb),SRGB_BYTES,ICC,'CMYK')
        np.testing.assert_array_equal(tif.asarray(),clean_u8(np.asarray(original),Settings(compensation=.5)))
    assert client.get(state['report_url']).json()['size']==[3201,59]
    assert client.post('/api/full-export/'+job+'/cancel').json()['status']=='complete'

def test_unknown_job():
    client=TestClient(app,headers={"X-Workspace":workspace_id})
    for route in ('','/file','/report'):
        assert client.get('/api/full-export/unknown'+route).status_code==404

def test_cmyk_preview_preserves_channels_and_icc(tmp_path):
    src=tmp_path/'big.tif'
    Image.new('CMYK',(3200,30),(250,180,50,20)).save(src,icc_profile=ICC)
    raster=inspect_raster(src)
    target=tmp_path/'small.tif';raster.save_preview(target)
    with Image.open(target) as im:
        assert im.mode=='CMYK';assert im.size==(2400,23)
        assert im.getpixel((100,10))==(250,180,50,20)
        assert im.info['icc_profile']==ICC
    preview,notes=inspect_raster(target).preview(ICC)
    assert preview.mode=='CMYK'
