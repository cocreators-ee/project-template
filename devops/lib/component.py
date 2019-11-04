import json
import random
from pathlib import Path
from shutil import copy
from typing import List, Optional

import yaml
from invoke import Context

from devops.lib.log import logger
from devops.lib.utils import label, run, merge_docs

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper


class ValidationError(Exception):
    pass


# Kubernetes resource types that do not need to be patched
SKIP_PATCH_KUBE_KINDS = (
    "ClusterRole",
    "ClusterRoleBinding",
    "Role",
    "RoleBinding",
    "ServiceAccount",
)

# https://kubernetes.io/docs/reference/generated/kubectl/kubectl-commands#rollout
RESTART_RESOURCES = ("Deployment", "DaemonSet", "StatefulSet")

# How long to wait for any rollout to successfully complete before failing
ROLLOUT_TIMEOUT = 5 * 60.0


class Component:
    def __init__(self, path: str):
        self._resources = None
        self.context = None
        self.image_pull_secrets = {}
        self.image = None
        self.image_prefix = ""
        self.name = self._path_to_name(path)
        self.namespace = None
        self.orig_path = Path(path)
        self.path = self.orig_path
        self.tag = "latest"
        self.replicas = None

        self.kube_configs = self._get_kube_configs()
        self.kube_merges = {}
        self.obsolete_kube_configs = self._get_obsolete_kube_configs()

    def __str__(self):
        ips = "set" if self.image_pull_secrets is not None else "not set"
        return (
            f"<Component "
            f"path={self.path} "
            f"image={self.image} "
            f"tag={self.tag} "
            f"ips={ips}>"
        )

    def validate(self, ctx=None):
        if not self.kube_configs:
            raise ValueError(f"No kube configs found in {self.path / 'kube'}")

        if not ctx:
            return

        for file in self.kube_configs:
            path = self.kube_configs[file]
            result = run(["kubeval", path])
            if result.returncode > 0:
                raise ValidationError(f"Validation failed for {path}")

    def build(self, ctx: Context, dry_run=False):
        label(logger.info, f"Building {self.path}")
        dockerfile = self.path / "Dockerfile"

        if not dockerfile.exists():
            logger.info(f"No Dockerfile for {self.name} component")
            return

        if dry_run:
            logger.info(f"[DRY RUN] Building {self.name} Docker image")
        else:
            logger.info(f"Building {self.name} Docker image")
            tag = self._get_full_docker_name()
            run(["docker", "build", self.path, "-t", tag], stream=True)

    def patch_from_env(self, env):
        env_path = Path("envs") / env / self.path.as_posix()
        for match in (env_path / "kube").glob("*.yaml"):
            logger.info(f"Found kube override {match.name} for {self.name} in {env}")
            self.kube_configs[match.name] = match

        merge_path = Path("envs") / env / "merges" / self.path.as_posix()
        for match in (merge_path / "kube").glob("*.yaml"):
            logger.info(f"Found kube merges {match.name} for {self.name} in {env}")
            self.kube_merges[match.name] = match

    def release(
        self, ctx: Context, rel_path: Path, dry_run: bool, no_rollout_wait: bool
    ):
        self._prepare_configs(rel_path)
        self._do_release(ctx, dry_run)
        self._restart_resources(ctx, dry_run, no_rollout_wait)
        self._post_release(ctx, dry_run)

    def _do_release(self, ctx: Context, dry_run: bool):
        for config in self.kube_configs:
            path = self.kube_configs[config]

            self._release_kube_config(ctx, path, dry_run)

        for config in self.obsolete_kube_configs:
            path = self.kube_configs[config]
            self._delete_kube_config(ctx, path, dry_run)

    def _post_release(self, ctx: Context, dry_run: bool):
        if not (self.orig_path / "post-release.sh").exists():
            return

        resources = self._get_resources()
        for resource in resources:
            data = resources[resource]
            if data["kind"] in RESTART_RESOURCES:
                self._try_post_release(ctx, resource, data["selector"], dry_run)

    def _try_post_release(
        self, ctx: Context, resource: str, selector: str, dry_run: bool
    ):
        if dry_run:
            logger.info(f"[DRY RUN] Running post-release.sh for {resource}")
            return

        result = run(
            [
                "kubectl",
                "-n",
                self.namespace,
                "get",
                "pods",
                "-l",
                selector,
                "-o",
                "json",
            ]
        )

        pods = []
        image = self._get_full_docker_name()
        for pod in json.loads(result.stdout)["items"]:
            for container in pod["spec"]["containers"]:
                if container["image"] == image:
                    pods.append(pod["metadata"]["name"])

        if not pods:
            raise Exception(f"No running pods with correct image found for {resource}")

        pod = random.choice(pods)  # nosec
        run(
            [
                "kubectl",
                "-n",
                self.namespace,
                "exec",
                "-it",
                pod,
                "sh",
                "post-release.sh",
            ],
            check=False,
        )

    def _release_kube_config(self, ctx: Context, config: Path, dry_run: bool):
        if dry_run:
            logger.info(f"[DRY RUN] Applying {config}")
            return

        logger.info(f"Applying {config}")
        run(["kubectl", "apply", "-f", config])

    def _delete_kube_config(self, ctx: Context, config: Path, dry_run: bool):
        if dry_run:
            logger.info(f"[DRY RUN] Deleting {config}")
            return

        logger.info(f"Deleting {config}")
        run(["kubectl", "delete", "-f", config])

    def _restart_resources(self, ctx: Context, dry_run: bool, no_rollout_wait: bool):
        resources = self._get_resources()
        for resource in resources:
            if resources[resource]["kind"] in RESTART_RESOURCES:
                self._restart_resource(ctx, resource, dry_run, no_rollout_wait)

    def _restart_resource(
        self, ctx: Context, resource: str, dry_run: bool, no_rollout_wait: bool
    ):
        if dry_run:
            logger.info(f"[DRY RUN] Restarting resource {resource}")
            return

        logger.info(f"Restarting resource {resource}")
        run(["kubectl", "-n", self.namespace, "rollout", "restart", resource])

        if not no_rollout_wait:
            run(
                ["kubectl", "-n", self.namespace, "rollout", "status", resource],
                timeout=ROLLOUT_TIMEOUT,
            )

    def _prepare_configs(self, dst: Path):
        dst = dst / self.path
        kube_dst = dst / "kube"
        kube_dst.mkdir(mode=700, parents=True)
        logger.info(f"Writing configs to {dst}")

        dockerfile = self.path / "Dockerfile"
        if dockerfile.exists():
            logger.info("Copying Dockerfile")
            copy(dockerfile, dst / "Dockerfile")

        for config in self.kube_configs:
            config_file = self.path / "kube" / config
            src = self.kube_configs[config]  # Incl. env patch
            logger.info(f"Patching {config_file}")
            with src.open("r") as f:
                docs = list(yaml.load_all(f, Loader))

            self._patch_yaml_docs(docs)

            if config in self.kube_merges:
                with self.kube_merges[config].open("r") as f:
                    overrides = list(yaml.load_all(f, Loader))
                docs = merge_docs(docs, overrides)

            dst_path = kube_dst / config
            with dst_path.open("w") as config_dst:
                yaml.dump_all(docs, stream=config_dst, Dumper=Dumper)

            self.kube_configs[config] = dst_path

        self.path = dst

    def _patch_yaml_docs(self, config: List[dict]):
        processed = []
        for doc in config:
            kind = doc["kind"]

            if kind in SKIP_PATCH_KUBE_KINDS:
                logger.info(f"Skipping {kind} patching")
                continue

            self._patch_generic(doc)
            if kind == "Deployment":
                self._patch_deployment(doc)
            elif kind == "DaemonSet":
                self._patch_daemon_set(doc)
            elif kind == "StatefulSet":
                self._patch_stateful_set(doc)

            processed.append(doc)

        return processed

    def _patch_generic(self, doc: dict):
        logger.info("Applying generic patches")
        meta = doc["metadata"]

        if self.namespace:
            logger.info(f"Updating namespace to {self.namespace}")
            meta["namespace"] = self.namespace

    def _patch_deployment(self, doc: dict):
        logger.info("Patching found Deployment")
        self._patch_containers(doc)
        self._patch_image_pull_secrets(doc)
        self._patch_replicas(doc)

    def _patch_daemon_set(self, doc: dict):
        logger.info("Patching found DaemonSet")
        self._patch_containers(doc)
        self._patch_image_pull_secrets(doc)
        self._patch_replicas(doc)

    def _patch_stateful_set(self, doc: dict):
        logger.info("Patching found StatefulSet")
        self._patch_containers(doc)
        self._patch_image_pull_secrets(doc)
        self._patch_replicas(doc)

    def _patch_containers(self, doc: dict):
        logger.info("Patching containers")
        containers = doc["spec"]["template"]["spec"]["containers"]
        for container in containers:
            image, tag = container["image"].split(":")
            if self.image:
                logger.info(f"Patching image from {image} to {self.image}")
                image = self.image
            if self.tag:
                logger.info(f"Patching tag from {tag} to {self.tag}")
                tag = self.tag
            container["image"] = f"{image}:{tag}"

    def _patch_replicas(self, doc: dict):
        spec = doc["spec"]
        if self.replicas and spec.get("replicas", None) is not None:
            spec["replicas"] = self.replicas

    def _patch_image_pull_secrets(self, doc: dict):
        spec = doc["spec"]
        containers = spec["template"]["spec"]["containers"]
        image = ""
        if self.image:
            image = self.image
        else:
            for container in containers:
                image, _ = container["image"].split(":")
                break

        if "/" in image:
            host, _ = image.split("/")
            if host in self.image_pull_secrets:
                secret = self.image_pull_secrets[host]
                logger.info(f"Patching imagePullSecrets to {secret}")
                tpl_spec = spec["template"]["spec"]
                tpl_spec["imagePullSecrets"] = [{"name": secret}]

    def _get_kube_configs(self, path=None):
        if path is None:
            path = self.path

        config = {}
        for match in (path / "kube").glob("*.yaml"):
            logger.info(f"Found kube config {match.name} for {self.name}")
            config[match.name] = match

        return config

    def _get_obsolete_kube_configs(self, path=None):
        if path is None:
            path = self.path

        obs_path = path / "kube" / "obsolete"

        configs = {}
        if not obs_path.exists():
            return configs

        for match in obs_path.glob("*.yaml"):
            logger.info(f"Found obsoleted kube config {match.name} for {self.name}")
            configs[match.name] = match

        return configs

    def _get_resources(self) -> dict:
        if self._resources:
            return self._resources

        self._resources = {}
        for config in self.kube_configs:
            config_file = self.kube_configs[config]
            with config_file.open("r") as f:
                docs = yaml.load_all(f, Loader)
                for doc in docs:
                    name = self._get_resource_name(doc)

                    self._resources[name] = {
                        "name": doc["metadata"]["name"],
                        "kind": doc["kind"],
                        "selector": self._get_selector(doc),
                    }

        return self._resources

    def _get_full_docker_name(self) -> str:
        prefix = self.image_prefix
        image = self.name
        tag = self.tag
        return f"{prefix}{image}:{tag}"

    @staticmethod
    def _get_resource_name(doc: dict) -> str:
        kind = doc["kind"]
        name = doc["metadata"]["name"]
        return f"{kind}/{name}"

    @staticmethod
    def _get_selector(doc: dict) -> Optional[str]:
        # spec.template.metadata.labels
        try:
            labels = doc["spec"]["template"]["metadata"]["labels"]
            for label in labels:
                return f"{label}={labels[label]}"
        except KeyError:
            return None

    @staticmethod
    def _path_to_name(path: str) -> str:
        return path.replace("/", "-")
