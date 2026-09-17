import pytest

from spacecraft_control import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}"})
    yield app
    app.extensions["mission"].stop()
    app.extensions["mission"].store.engine.dispose()


@pytest.fixture
def mission(app):
    return app.extensions["mission"]


@pytest.fixture
def client(app):
    return app.test_client()
