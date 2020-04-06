from pathlib import Path
from shutil import rmtree

import pytest

ENVS_PATH = Path("envs")
TEST_ENV = "unit_test_env_6zxuj"
TEST_ENV_PATH = ENVS_PATH / TEST_ENV

TEST_COMPONENT_PATH = Path("service/TEST_COMPONENT_LOL")


@pytest.fixture()
def clean_test_settings():
    delete_test_settings()
    yield None
    delete_test_settings()


@pytest.fixture()
def clean_test_component():
    delete_test_component()
    yield None
    delete_test_component()


def delete_test_settings():
    if TEST_ENV_PATH.exists():
        rmtree(TEST_ENV_PATH)


def delete_test_component():
    if TEST_COMPONENT_PATH.exists():
        rmtree(TEST_COMPONENT_PATH)
