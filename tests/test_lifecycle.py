import io
import re
import threading
import time
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image
import app as server
from cleaner.full_export import Cancelled


def client():
    return TestClient(server.app,headers={'X-Workspace':server.workspace_id})

def open_page(c):
    html=c.get('/')
    key=re.search('name="workspace-id" content="([a-f0-9]+)"',html.text)[1]
    c.headers['X-Workspace']=key
    assert c.post('/api/workspace/open').status_code==200
    return key

def upload(c,color=(50,80,120)):
    buf=io.BytesIO();Image.new('RGB',(128,90),color).save(buf,format='PNG')
    r=c.post('/api/upload',files={'file':('file.png',buf.getvalue(),'image/png')})
    assert r.status_code==200,r.text
    return r.json()['id']

def process(c,key):
    r=c.post('/api/process',json={'source':key})
    assert r.status_code==200,r.text
    return r.json()['id']

def test_reload_clears_materials_and_keeps_requested_defaults(tmp_path):
    c=client();old_page=open_page(c)
    key=upload(c);token=process(c,key)
    original=server.sources[key]
    assert isinstance(server.source_previews[key],Image.Image)
    assert list(server.UPLOADS.iterdir())==[original]  # no on-disk preview cache
    saved=tmp_path/'user-saved.tif';saved.write_bytes(b'keep this external file')
    open_page(c)
    assert not original.exists();assert not server.RUNTIME.exists()
    assert not server.results and not server.source_previews and not server.sources
    assert c.get('/api/export/'+token).status_code==410
    assert c.post('/api/process',json={'source':key}).status_code==404
    assert saved.read_bytes()==b'keep this external file'
    catalog=c.get('/api/catalog').json()
    assert catalog['samples']==[]
    assert catalog['defaults']=={'strength':1,'compensation':.82,'max_k':100,'neutral_protection':1,'tac':300,'smooth_ties':True}
    assert c.post('/api/upload',headers={'X-Workspace':old_page},files={'file':('late.png',b'invalid','image/png')}).status_code==409
    assert not server.RUNTIME.exists()

def test_new_file_deletes_previous_file_and_full_exports():
    c=client();old=upload(c);token=process(c,old)
    old_path=server.sources[old]
    job=c.post('/api/full-export/'+token).json()['id']
    for _ in range(200):
        state=c.get('/api/full-export/'+job).json()
        if state['status']=='complete':break
        time.sleep(.005)
    assert state['status']=='complete',state
    output=server.jobs[job]['path'];assert output.exists()
    new=upload(c,(60,70,80))
    assert not old_path.exists() and not output.exists() and not output.with_suffix('.json').exists()
    assert set(server.sources)=={new};assert set(server.source_previews)=={new}
    assert c.get('/api/full-export/'+job).status_code==404
    assert c.get('/api/export/'+token).status_code==410
    assert len(list(server.UPLOADS.iterdir()))==1

def test_new_file_cancels_writer_before_removing_input(monkeypatch):
    c=client();old=upload(c);token=process(c,old)
    old_path=server.sources[old];started=threading.Event();stopped=threading.Event()
    def blocked(source,target,settings,destination,progress,cancelled):
        started.set()
        try:
            for _ in range(400):
                if cancelled():
                    assert old_path.exists(), 'Input deleted while worker still running'
                    raise Cancelled()
                time.sleep(.005)
            raise AssertionError('Worker was not cancelled')
        finally: stopped.set()
    monkeypatch.setattr(server,'export_full',blocked)
    assert c.post('/api/full-export/'+token).status_code==200
    assert started.wait(1)
    new=upload(c,(10,30,40))
    assert stopped.is_set() and not old_path.exists()
    assert set(server.sources)=={new} and not server.jobs

def test_old_page_beacon_cannot_delete_new_page_file():
    c=client();old=open_page(c)
    upload(c);new=open_page(c);key=upload(c)
    assert c.post(f'/api/workspace/{old}/close').status_code==204
    assert server.sources[key].exists()
    assert c.post(f'/api/workspace/{new}/close').status_code==204
    assert not server.RUNTIME.exists() and not server.sources

def test_html_health_check_does_not_clear_active_material():
    c=client();key=upload(c)
    assert c.get('/').status_code==200
    assert server.sources[key].exists()

def test_unsupported_replacement_still_discards_previous_file():
    c=client();key=upload(c);old=server.sources[key]
    r=c.post('/api/upload',files={'file':('unsupported.pdf',b'bad','application/pdf')})
    assert r.status_code==422
    assert not old.exists() and not server.RUNTIME.exists()

def test_restart_cleanup_removes_abandoned_working_files():
    for folder in (server.UPLOADS,server.FULL_OUTPUT):
        folder.mkdir(parents=True,exist_ok=True)
        (folder/'abandoned.part').write_bytes(b'temporary')
    server.reset_workspace()
    assert not server.RUNTIME.exists()
