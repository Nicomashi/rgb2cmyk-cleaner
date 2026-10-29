import io
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
import app as server
from cleaner.color import SRGB_BYTES, convert, preview
from cleaner.engine import Settings, clean_u8


def prepare(image,icc=SRGB_BYTES,settings=None):
    client=TestClient(server.app,headers={'X-Workspace':server.workspace_id})
    buf=io.BytesIO();image.save(buf,format='TIFF',icc_profile=icc)
    source=client.post('/api/upload',files={'file':('test.tif',buf.getvalue())}).json()['id']
    response=client.post('/api/process',json={'source':source,**({'settings':settings} if settings else {})})
    assert response.status_code==200,response.text
    return client,response.json()


def test_sampler_reads_original_not_thumbnail():
    a=np.zeros((4,3000,3),dtype=np.uint8);a[:]=[20,50,90];a[2,1501]=[239,172,31]
    client,result=prepare(Image.fromarray(a))
    assert result['width']<3000
    r=client.post('/api/samples/'+result['id'],json={'points':[{'x':1501,'y':2}],'area':1})
    assert r.status_code==200,r.text
    assert r.json()['basis']=='original'
    p=r.json()['points'][0]
    assert p['source']==[239,172,31]
    assert p['swatch_before']==[239,172,31]
    icc=server.PROFILE.read_bytes()
    separated=convert(Image.new('RGB',(1,1),(239,172,31)),SRGB_BYTES,icc,'CMYK')
    np.testing.assert_allclose(p['before'],np.round(np.asarray(separated)[0,0].astype(float)*100/255,1))
    assert p['swatch_cmyk_before']==list(preview(separated,icc).getpixel((0,0)))


def test_mean_is_after_pixelwise_cleaning_and_clips_edges():
    a=np.array([[[230,180,40,20],[50,200,150,15]],[[50,50,50,30],[200,120,70,5]]],dtype=np.uint8)
    icc=server.PROFILE.read_bytes()
    client,result=prepare(Image.fromarray(a,'CMYK'),icc)
    p=client.post('/api/samples/'+result['id'],json={'points':[{'x':0,'y':0}],'area':5}).json()['points'][0]
    np.testing.assert_allclose(p['source'],np.round(a.astype(float).mean((0,1))*100/255,1))
    expected=clean_u8(a,Settings()).astype(float).mean((0,1))*100/255
    np.testing.assert_allclose(p['after'],np.round(expected,1))
    assert p['tac']==round(float(expected.sum()),1)
    assert len(p['swatch_after'])==3


def test_settings_changes_update_same_probe_and_validate_input():
    a=Image.new('CMYK',(12,8),(230,180,40,20));icc=server.PROFILE.read_bytes()
    c,first=prepare(a,icc)
    req={'points':[{'x':2,'y':3}],'area':1}
    p=c.post('/api/samples/'+first['id'],json=req).json()['points'][0]
    source=next(iter(server.sources))
    second=c.post('/api/process',json={'source':source,'settings':{'strength':0}}).json()
    q=c.post('/api/samples/'+second['id'],json=req).json()['points'][0]
    assert p['source']==q['source'] and p['after']!=q['after']
    assert p['before']==q['before']
    assert q['before']==q['after']
    assert q['swatch_cmyk_before']==q['swatch_after']
    assert c.post('/api/samples/'+second['id'],json={**req,'area':2}).status_code==422
    assert c.post('/api/samples/'+second['id'],json={'points':[{'x':12,'y':0}]}).status_code==422
    assert c.post('/api/samples/'+second['id'],json=req,headers={'X-Workspace':'stale'}).status_code==409
    assert c.post('/api/materials/clear').status_code==204
    assert not server.RUNTIME.exists()
    assert c.post('/api/samples/'+second['id'],json=req).status_code==410


def test_demo_is_explicit_and_new_material_replaces_it():
    c=TestClient(server.app,headers={'X-Workspace':server.workspace_id})
    assert c.get('/api/catalog').json()['samples']==[]
    assert not server.sources
    r=c.post('/api/demo');assert r.status_code==200,r.text
    path=server.sources[r.json()['id']];assert path.exists()
    c.post('/api/materials/clear')
    assert not path.exists()
    assert (server.ROOT/'static/demo.jpg').exists()
    assert c.get('/static/demo.jpg').headers['cache-control']=='no-store'


def test_new_export_removes_previous_export_files():
    import time
    client,result=prepare(Image.new('RGB',(16,12),(30,70,120)))
    first=client.post('/api/full-export/'+result['id']).json()['id']
    for _ in range(200):
        if client.get('/api/full-export/'+first).json()['status']=='complete': break
        time.sleep(.01)
    old=server.jobs[first]['path']
    assert old.exists()
    second=client.post('/api/full-export/'+result['id'])
    assert second.status_code==200
    assert not old.exists() and not old.with_suffix('.json').exists()
    assert client.get('/api/full-export/'+first).status_code==404
