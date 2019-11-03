import json
from io import StringIO

import yaml

from devops.lib.component import Component

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
---
spec:
  template:
    spec:
      containers:
        -
        - volumeMounts:
            - mountPath: /var/run/docker.sock
              name: docker-volume
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

DEPLOYMENT = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-deployment
spec:
  replicas: 2
  selector:
    matchLabels:
      app: test-deployment
  template:
    metadata:
      labels:
        app: test-deployment
    spec:
      containers:
        - name: test-deployment
          imagePullPolicy: IfNotPresent
          image: imagined.registry.tld/myproj-service-test-deployment:latest
"""


def get_deployment() -> dict:
    return yaml.load(StringIO(DEPLOYMENT), yaml.Loader)


def test_get_full_docker_name():
    c = Component("service/test-service")
    assert c._get_full_docker_name() == "service-test-service:latest"

    c = Component("service/test-service")
    c.image_prefix = "myproj-"
    c.tag = "v1.2.3"
    assert c._get_full_docker_name() == "myproj-service-test-service:v1.2.3"


def test_patch_containers():
    deploy = get_deployment()
    c = Component("service/test-service")
    c.image = "test-image"
    c.tag = "v6.6.6"
    c._patch_containers(deploy)

    container = deploy["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "test-image:v6.6.6"


def test_patch_image_pull_secrets():
    deploy = get_deployment()
    c = Component("service/test-service")
    c.image_pull_secrets = {"imagined.registry.tld": "secret"}
    c._patch_image_pull_secrets(deploy)
    spec = deploy["spec"]["template"]["spec"]
    assert spec["imagePullSecrets"][0]["name"] == "secret"


def test_patch_replicas():
    deploy = get_deployment()
    c = Component("service/test-service")
    c.replicas = 77
    c._patch_replicas(deploy)

    assert deploy["spec"]["replicas"] == 77


def test_kube_merge():
    docs = list(yaml.load_all(StringIO(MERGE_TEST), yaml.Loader))
    overrides = list(yaml.load_all(StringIO(MERGE_CHANGES), yaml.BaseLoader))
    expected = list(yaml.load_all(StringIO(MERGE_EXPECTED), yaml.Loader))

    merged = Component._merge_docs(docs, overrides)
    for i, merged_doc in enumerate(merged):
        expected_doc = expected[i]

        merged_json = json.dumps(merged_doc, **JSON_FORMAT)
        expected_json = json.dumps(expected_doc, **JSON_FORMAT)

        print(f"Doc {i + 1} expected: {expected_json}")
        print(f"Doc {i + 1} actual  : {merged_json}")

        assert merged_json == expected_json


def test_readme_kube_merge():
    docs = list(yaml.load_all(StringIO(README_MERGE_SRC), yaml.Loader))
    overrides = list(yaml.load_all(StringIO(README_MERGE_OVERRIDE), yaml.BaseLoader))
    expected = list(yaml.load_all(StringIO(README_MERGE_EXPECTED), yaml.Loader))

    merged = Component._merge_docs(docs, overrides)
    for i, merged_doc in enumerate(merged):
        expected_doc = expected[i]

        merged_json = json.dumps(merged_doc, **JSON_FORMAT)
        expected_json = json.dumps(expected_doc, **JSON_FORMAT)

        print(f"Doc {i + 1} expected: {expected_json}")
        print(f"Doc {i + 1} actual  : {merged_json}")

        assert merged_json == expected_json
