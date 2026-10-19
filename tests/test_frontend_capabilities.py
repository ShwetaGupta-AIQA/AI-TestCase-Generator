from unittest.mock import patch
from fastapi.testclient import TestClient
from api.main import app
from api.demo import app as demo


def test_full_backend_advertises_features_without_secrets():
    with patch.dict('os.environ', {'TESTGEN_REQUIRE_WORKSPACE':'true', 'TESTGEN_ENABLE_RENDERED_INSPECTION':'false', 'OPENROUTER_API_KEY':'private-key'}):
        response = TestClient(app).get('/capabilities')
        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'durable'
        assert data['workspace_required'] is True
        assert all(data['features'][key] for key in ['requirements','documents','api_testing','web_testing','history'])
        assert data['features']['rendered_inspection'] is False
        assert data['limits']['upload_bytes'] == 10 * 1024 * 1024
        assert 'private-key' not in response.text


def test_guest_demo_does_not_advertise_unimplemented_routes():
    with patch.dict('os.environ', {'TESTGEN_REQUIRE_WORKSPACE':'true', 'TESTGEN_ENABLE_RENDERED_INSPECTION':'true'}):
        response = TestClient(demo).get('/capabilities')
        data = response.json()
        assert data['mode'] == 'demo'
        assert data['features']['requirements'] is True
        assert data['workspace_required'] is False
        assert not any(data['features'][key] for key in ['api_testing','web_testing','history','rendered_inspection'])
        assert data['limits']['requirement_chars'] > 0
        assert response.headers['Cache-Control'] == 'no-store'


def test_rendered_support_matches_server_flag():
    with patch.dict('os.environ', {'TESTGEN_REQUIRE_WORKSPACE':'false','TESTGEN_ENABLE_RENDERED_INSPECTION':'true'}):
        data = TestClient(app).get('/capabilities').json()
        assert data['features']['rendered_inspection'] is True
        assert data['workspace_required'] is False
