import base64
import io
from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image
from app import app,ROOT,workspace_id
from cleaner.color import SRGB_BYTES,convert

client=TestClient(app,headers={"X-Workspace":workspace_id})
ICC=(ROOT/'profiles/source-fogra39.icc').read_bytes()

def pixels(uri):
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(uri.split(',',1)[1]))))

def upload(image,icc):
    buf=io.BytesIO();image.save(buf,format='TIFF',icc_profile=icc)
    r=client.post('/api/upload',files={'file':('source.tif',buf.getvalue(),'image/tiff')})
    assert r.status_code==200,r.text
    return r.json()['id']

def test_rgb_left_is_original_without_cmyk_roundtrip():
    original=Image.new('RGB',(12,8),(0,255,30))
    key=upload(original,SRGB_BYTES)
    native=client.post('/api/process',json={'source':key}).json()
    proof=client.post('/api/process',json={'source':key,'before_mode':'cmyk'}).json()
    assert native['left_label']=='Исходник · RGB'
    np.testing.assert_array_equal(pixels(native['before']),np.asarray(original))
    assert not np.array_equal(pixels(native['before']),pixels(proof['before']))
    np.testing.assert_array_equal(pixels(native['after']),pixels(proof['after']))
    p=client.get(f"/api/pixel/{native['id']}?x=0&y=0").json()
    assert p['source_mode']=='RGB';assert p['source_pixel']==[0,255,30]

def test_cmyk_left_uses_source_icc_before_cleanup():
    original=Image.new('CMYK',(12,8),(255,220,68,35))
    key=upload(original,ICC)
    response=client.post('/api/process',json={'source':key}).json()
    assert response['source_mode']=='CMYK'
    np.testing.assert_array_equal(pixels(response['before']),np.asarray(convert(original,ICC,SRGB_BYTES,'RGB')))
    p=client.get(f"/api/pixel/{response['id']}?x=0&y=0").json()
    assert p['source_pixel']==[255,220,68,35]

def test_non_srgb_input_uses_its_profile():
    # The app itself runs on macOS; skip on platforms without this optional fixture.
    import pytest
    path=Path('/System/Library/ColorSync/Profiles/AdobeRGB1998.icc')
    if not path.exists(): pytest.skip('Adobe RGB fixture unavailable')
    icc=path.read_bytes();original=Image.new('RGB',(12,8),(100,160,90))
    key=upload(original,icc)
    r=client.post('/api/process',json={'source':key}).json()
    expected=np.asarray(convert(original,icc,SRGB_BYTES,'RGB'))
    np.testing.assert_array_equal(pixels(r['before']),expected)
    assert not np.array_equal(expected,np.asarray(original))

def test_channels_compare_target_separations_not_rgb():
    key=upload(Image.new('RGB',(12,8),(0,255,30)),SRGB_BYTES)
    a=client.post('/api/process',json={'source':key,'channel':'C'}).json()
    b=client.post('/api/process',json={'source':key,'channel':'C','before_mode':'cmyk'}).json()
    assert a['comparison']=='cmyk'
    assert a['left_label']=='C до очистки'
    np.testing.assert_array_equal(pixels(a['before']),pixels(b['before']))

def test_invalid_comparison():
    assert client.post('/api/process',json={'before_mode':'invented'}).status_code==422
