import sys
from importlib import invalidate_caches
from pathlib import Path
from shutil import rmtree

import pytest
from devops.lib.utils import list_envs, load_env_settings, run

TEST_ENV = "unit_test_env_6zxuj"
TEST_ENV_PATH = Path("envs") / TEST_ENV
TEST_ENV_SETTINGS = TEST_ENV_PATH / "settings.py"

TEST_SETTINGS = """
COMPONENTS = ["service/TEST_COMPONENT_LOL"]
KUBE_CONTEXT = "TEST_CONTEXT_LOL"
KUBE_NAMESPACE = "TEST_NAMESPACE_LOL"
"""

TEST_FULL_SETTINGS = (
    TEST_SETTINGS
    + """
REPLICAS = {"service/TEST_COMPONENT_LOL": 3}
IMAGE_PULL_SECRETS = {"service/TEST_COMPONENT_LOL": "secret"}
"""
)


def clean_caches():
    for path in Path(".").rglob("__pycache__"):
        rmtree(path)
    invalidate_caches()


def delete_test_settings():
    if TEST_ENV_PATH.exists():
        rmtree(TEST_ENV_PATH)


@pytest.fixture()
def clean_test_settings():
    delete_test_settings()
    yield None
    delete_test_settings()


def test_load_env_settings(clean_test_settings):
    envs = list_envs()
    settings = load_env_settings(envs[0])

    getattr(settings, "IMAGE_PULL_SECRETS")
    getattr(settings, "KUBE_CONTEXT")
    getattr(settings, "KUBE_NAMESPACE")
    getattr(settings, "COMPONENTS")
    getattr(settings, "REPLICAS")

    TEST_ENV_PATH.mkdir(parents=True)
    TEST_ENV_SETTINGS.write_text(TEST_SETTINGS)

    settings = load_env_settings(TEST_ENV)
    assert len(settings.COMPONENTS) == 1
    assert "service/TEST_COMPONENT_LOL" in settings.COMPONENTS
    assert settings.KUBE_CONTEXT == "TEST_CONTEXT_LOL"
    assert settings.KUBE_NAMESPACE == "TEST_NAMESPACE_LOL"
    assert len(settings.IMAGE_PULL_SECRETS) == 0
    assert len(settings.REPLICAS) == 0


def test_run():
    res = run(["python", "--version"])
    ver = sys.version.split(" ")[0]
    assert res.stdout.decode("utf-8").strip() == f"Python {ver}"
