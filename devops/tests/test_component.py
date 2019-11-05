from io import StringIO

import yaml

from devops.lib.component import Component

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
