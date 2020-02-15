import json
import sys
from importlib import invalidate_caches
from io import StringIO
from pathlib import Path
from shutil import rmtree

import pytest
import yaml

from devops.lib.utils import list_envs, load_env_settings, merge_docs, run

ENVS_PATH = Path("envs")
TEST_ENV = "unit_test_env_6zxuj"
TEST_ENV_PATH = ENVS_PATH / TEST_ENV
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

# Human and computer diffable JSON format
JSON_FORMAT = {"sort_keys": True, "indent": 2, "separators": (", ", ": ")}

MERGE_TEST = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: myproj-constants
data:
  UNCHANGED_SETTING: "value"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: myproj-settings
data:
  MY_SETTING: "foo"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: big-deployment
spec:
  replicas: 2
  selector:
    matchLabels:
      app: big-deployment
  template:
    metadata:
      labels:
        app: big-deployment
    spec:
      containers:
        - name: first-container
          imagePullPolicy: IfNotPresent
          image: first-container:latest
        - name: second-container
          imagePullPolicy: IfNotPresent
          image: second-container:latest
        - name: third-container
          imagePullPolicy: Never
          image: third-container:latest
      volumes:
        - name: some-data
          persistentVolumeClaim:
            claimName: some-data
"""

MERGE_CHANGES = """
---
---
data:
  MY_SETTING: "bar"
  DEBUG: 'True'
---
spec:
  template:
    spec:
      containers:
        -
        - volumeMounts:
            - mountPath: /var/run/docker.sock
              name: docker-volume
        - securityContext:
            allowPrivilegeEscalation: true
      volumes:
        - persistentVolumeClaim: ~
        - name: docker-volume
          hostPath:
            path: /var/run/docker.sock
"""

MERGE_EXPECTED = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: myproj-constants
data:
  UNCHANGED_SETTING: "value"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: myproj-settings
data:
  MY_SETTING: "bar"
  DEBUG: 'True'
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: big-deployment
spec:
  replicas: 2
  selector:
    matchLabels:
      app: big-deployment
  template:
    metadata:
      labels:
        app: big-deployment
    spec:
      containers:
        - name: first-container
          imagePullPolicy: IfNotPresent
          image: first-container:latest
        - name: second-container
          imagePullPolicy: IfNotPresent
          image: second-container:latest
          volumeMounts:
            - mountPath: /var/run/docker.sock
              name: docker-volume
        - name: third-container
          imagePullPolicy: Never
          image: third-container:latest
          securityContext:
            allowPrivilegeEscalation: true
      volumes:
        - name: some-data
        - name: docker-volume
          hostPath:
            path: /var/run/docker.sock
"""

README_MERGE_SRC = """
# component/kube/01-example.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: myproj-settings
data:
  MY_SETTING: "foo"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-deployment
spec:
  selector:
    matchLabels:
      app: my-deployment
  template:
    metadata:
      labels:
        app: my-deployment
    spec:
      containers:
        - name: my-container
          imagePullPolicy: IfNotPresent
          image: my-container:latest
          env:
            - name: ANOTHER_SETTING
              value: some-value
          volumeMounts:
            - mountPath: /var/run/docker.sock
              name: docker-volume
"""

README_MERGE_OVERRIDE = """
# envs/test/merges/component/kube/01-example.yaml
data:
  MY_SETTING: "bar"
---
spec:
  template:
    spec:
      containers:
        - env:
            - name: ANOTHER_SETTING # this prop is here just for clarity
              value: another-value
          volumeMounts: ~
          livenessProbe:
            exec:
              command:
               - cat
               - /tmp/healthy
            initialDelaySeconds: 5
            periodSeconds: 5
"""

README_MERGE_EXPECTED = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: myproj-settings
data:
  MY_SETTING: "bar"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-deployment
spec:
  selector:
    matchLabels:
      app: my-deployment
  template:
    metadata:
      labels:
        app: my-deployment
    spec:
      containers:
        - name: my-container
          imagePullPolicy: IfNotPresent
          image: my-container:latest
          env:
            - name: ANOTHER_SETTING
              value: another-value
          livenessProbe:
            exec:
              command:
               - cat
               - /tmp/healthy
            initialDelaySeconds: 5
            periodSeconds: 5
"""


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


def test_kube_merge():
    docs = list(yaml.load_all(StringIO(MERGE_TEST), yaml.Loader))
    overrides = list(yaml.load_all(StringIO(MERGE_CHANGES), yaml.Loader))
    base_overrides = list(yaml.load_all(StringIO(MERGE_CHANGES), yaml.BaseLoader))
    expected = list(yaml.load_all(StringIO(MERGE_EXPECTED), yaml.Loader))

    merged = merge_docs(docs, overrides, base_overrides)
    for i, merged_doc in enumerate(merged):
        expected_doc = expected[i]

        merged_json = json.dumps(merged_doc, **JSON_FORMAT)
        expected_json = json.dumps(expected_doc, **JSON_FORMAT)

        print(f"Doc {i + 1} expected: {expected_json}")
        print(f"Doc {i + 1} actual  : {merged_json}")

        assert merged_json == expected_json


def test_readme_kube_merge():
    docs = list(yaml.load_all(StringIO(README_MERGE_SRC), yaml.Loader))
    overrides = list(yaml.load_all(StringIO(README_MERGE_OVERRIDE), yaml.Loader))
    base_overrides = list(
        yaml.load_all(StringIO(README_MERGE_OVERRIDE), yaml.BaseLoader)
    )
    expected = list(yaml.load_all(StringIO(README_MERGE_EXPECTED), yaml.Loader))

    merged = merge_docs(docs, overrides, base_overrides)
    for i, merged_doc in enumerate(merged):
        expected_doc = expected[i]

        merged_json = json.dumps(merged_doc, **JSON_FORMAT)
        expected_json = json.dumps(expected_doc, **JSON_FORMAT)

        print(f"Doc {i + 1} expected: {expected_json}")
        print(f"Doc {i + 1} actual  : {merged_json}")

        assert merged_json == expected_json


@pytest.mark.parametrize("folder", ["__foo__", ".bar"])
def test_list_envs(folder):
    path = ENVS_PATH / folder
    path.mkdir()
    try:
        envs = list_envs()

        assert folder not in envs
        assert "minikube" in envs
    finally:
        path.rmdir()
