import io
import base64
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageCms
from app import app, ROOT, workspace_id
from cleaner.color import SRGB_BYTES, description

client=TestClient(app,headers={"X-Workspace":workspace_id})

@pytest.fixture
def processed():
    buf=io.BytesIO(); Image.new('CMYK',(2400,420),(230,190,60,20)).save(buf,format='TIFF',icc_profile=(ROOT/'profiles/source-fogra39.icc').read_bytes())
    upload=client.post('/api/upload',files={'file':('sample.tif',buf.getvalue(),'image/tiff')})
    r=client.post('/api/process',json={'source':upload.json()['id']})
    assert r.status_code==200,r.text
    return r.json()

def test_catalog():
    r=client.get('/api/catalog'); assert r.status_code==200
    assert r.json()['samples']==[]
    assert 'FOGRA39' in r.json()['profile']

def test_preview(processed):
    assert processed['before'].startswith('data:image/png;base64,')
    with Image.open(io.BytesIO(base64.b64decode(processed['before'].split(',',1)[1]))) as im:
        assert im.size==(processed['width'],processed['height'])
    assert (processed['width'],processed['height'])==(2400,420)
    assert processed['stats']['changed_pct']>0

def test_pixel(processed):
    r=client.get(f"/api/pixel/{processed['id']}?x=2000&y=200")
    assert r.status_code==200
    d=r.json(); assert len(d['after'])==4
    assert client.get(f"/api/pixel/{processed['id']}?x=99999&y=0").status_code==422

def test_export_tiff(processed):
    r=client.get('/api/export/'+processed['id'])
    assert r.status_code==200
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.mode=='CMYK'; assert im.size==(2400,420)
        assert im.info['icc_profile']==(ROOT/'profiles/source-fogra39.icc').read_bytes()
        assert 'FOGRA39' in description(im.info['icc_profile'])
        assert im.tag_v2[258]==(8,8,8,8)
        assert np.asarray(im).shape==(420,2400,4)

def test_png_and_report(processed):
    r=client.get('/api/export/'+processed['id']+'?kind=png')
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.mode=='RGB'; assert im.info['icc_profile']==SRGB_BYTES
    r=client.get('/api/export/'+processed['id']+'?kind=report')
    assert r.json()['settings']['compensation']==.82
    assert r.json()['stats']==processed['stats']

@pytest.mark.parametrize('body',[{'source':'../../etc/passwd'},{'settings':{'strength':2}},{'channel':'bad'},{'profile':'bad'}])
def test_bad_requests(body):
    assert client.post('/api/process',json=body).status_code in (404,422)

def test_expired_result():
    assert client.get('/api/export/missing').status_code==410

def test_rgb_upload_with_profile():
    buf=io.BytesIO(); Image.new('RGB',(10,10),(45,90,200)).save(buf,format='PNG',icc_profile=SRGB_BYTES)
    r=client.post('/api/upload',files={'file':('test.png',buf.getvalue(),'image/png')})
    assert r.status_code==200
    result=client.post('/api/process',json={'source':r.json()['id']})
    assert result.status_code==200; assert result.json()['width']==10

def test_reject_unprofiled_cmyk():
    buf=io.BytesIO(); Image.new('CMYK',(10,10)).save(buf,format='TIFF')
    r=client.post('/api/upload',files={'file':('bad.tif',buf.getvalue(),'image/tiff')})
    assert r.status_code==422; assert 'ICC' in r.json()['detail']

def test_profile_upload_rejects_rgb():
    r=client.post('/api/profile',files={'file':('rgb.icc',SRGB_BYTES,'application/octet-stream')})
    assert r.status_code==422

def test_profile_upload_cmyk():
    r=client.post('/api/profile',files={'file':('out.icc',(ROOT/'profiles/source-fogra39.icc').read_bytes(),'application/octet-stream')})
    assert r.status_code==200; assert 'FOGRA39' in r.json()['name']

def test_16bit_rejected():
    buf=io.BytesIO(); Image.fromarray(np.zeros((4,4),dtype=np.uint16)).save(buf,format='TIFF')
    assert client.post('/api/upload',files={'file':('16.tif',buf.getvalue(),'image/tiff')}).status_code==422

@pytest.mark.parametrize('channel',['C','M','Y','K','map'])
def test_channels(channel):
    # Small RGB fixture exercises all render paths cheaply.
    buf=io.BytesIO(); Image.new('RGB',(8,8),(30,60,90)).save(buf,format='PNG')
    source=client.post('/api/upload',files={'file':('tiny.png',buf.getvalue(),'image/png')}).json()['id']
    r=client.post('/api/process',json={'source':source,'channel':channel})
    assert r.status_code==200; assert r.json()['after'].startswith('data:image/png;base64,')

def test_16bit_rgb_png_rejected():
    import struct,zlib
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,16,2,0,0,0))
    data+=chunk(b'IDAT',zlib.compress(b'\x00'+b'\x12\x34'*3))+chunk(b'IEND',b'')
    r=client.post('/api/upload',files={'file':('16.png',data,'image/png')})
    assert r.status_code==422; assert '16-битные' in r.json()['detail']
