"""Keep tests isolated from the user’s materials and restore the session token."""
import pytest
import app as app_module

@pytest.fixture(autouse=True)
def isolate_artifacts(tmp_path,monkeypatch):
    runtime=tmp_path/'runtime'
    monkeypatch.setattr(app_module,'RUNTIME',runtime)
    monkeypatch.setattr(app_module,'UPLOADS',runtime/'uploads')
    monkeypatch.setattr(app_module,'FULL_OUTPUT',runtime/'exports')
    original_session=app_module.workspace_id
    with app_module.work_lock: app_module.clear_materials()
    yield
    with app_module.work_lock: app_module.clear_materials()
    app_module.workspace_id=original_session
