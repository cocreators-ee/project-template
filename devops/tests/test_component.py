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

CRONJOB = """
apiVersion: batch/v1beta1
kind: CronJob
metadata:
  name: test-cronjob
spec:
  schedule: '* * * * *'
  jobTemplate:
    spec:
      replicas: 1
      template:
        metadata:
          labels:
            app: test-cronjob
        spec:
          containers:
            - name: test-cronjob
              imagePullPolicy: IfNotPresent
              image: imagined.registry.tld/myproj-service-test-cronjob:latest
"""


def get_deployment() -> dict:
    return yaml.load(StringIO(DEPLOYMENT), yaml.Loader)


def get_cronjob() -> dict:
    return yaml.load(StringIO(CRONJOB), yaml.Loader)


def test_get_docker_repository():
    c = Component("service/test-service")
    c.image_prefix = ""
    assert c.get_docker_repository() == f"service-test-service"

    c = Component("service/test-service")
    c.image_prefix = "myproj-"
    assert c.get_docker_repository() == f"myproj-service-test-service"


def test_get_full_docker_name():
    c = Component("service/test-service")
    c.image_prefix = ""
    assert c._get_full_docker_name() == "service-test-service:latest"

    c = Component("service/test-service")
    c.image_prefix = "myproj-"
    c.tag = "v1.2.3"
    assert c._get_full_docker_name() == "myproj-service-test-service:v1.2.3"


def test_patch_containers():
    deploy = get_deployment()
    c = Component("service/test-service")
    c.image_prefix = ""
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


def test_patch_cronjob():
    cronjob = get_cronjob()
    c = Component("service/test-cronjob")
    c.replicas = 77
    c.image_pull_secrets = {"imagined.registry.tld": "secret"}
    c.image_prefix = ""
    c.image = "imagined.registry.tld/test-image"
    c.tag = "v6.6.7"

    c._patch_cronjob(cronjob)
    # Assert image
    spec = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    cronjob_image = spec["containers"][0]["image"]
    assert cronjob_image == "imagined.registry.tld/test-image:v6.6.7"
    # Assert imagePullSecrets
    assert spec["imagePullSecrets"][0]["name"] == "secret"
    # Assert replicas
    assert cronjob["spec"]["jobTemplate"]["spec"]["replicas"] == 77
