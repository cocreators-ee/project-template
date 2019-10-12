import random
import string
from pathlib import Path
from shutil import rmtree
from typing import List

from invoke import Context

from devops.lib.component import Component
from devops.lib.log import logger
from devops.lib.utils import list_envs, load_env_settings, big_label, label, run
from devops.settings import IMAGE_PREFIX

RELEASE_TMP = Path("temp")


def generate_release_id() -> str:
    length = 5
    chars = string.ascii_lowercase + string.digits

    return "".join(random.choice(chars) for _ in range(length))


def build_images(ctx, components, dry_run=False):
    big_label(logger.info, "Building images")
    for c in components:
        component = Component(c)
        component.image_prefix = IMAGE_PREFIX
        component.build(ctx, dry_run)


def validate_release_configs(ctx):
    envs = list_envs()
    for env in envs:
        logger.info("Validating configs for {} environment".format(env))
        settings = load_env_settings(env)
        components = settings.COMPONENTS

        for path in components:
            component = Component(path)
            component.validate(ctx)
            component.patch_from_env(env)
            component.validate(ctx)


def ensure_context(context):
    """
    Ensure Kubernetes CLI is using the given context
    :param str context:
    """
    run(["kubectl", "config", "use-context", context])


def ensure_namespace(namespace):
    """
    Ensure Kubernetes cluster has the given namespace
    :param str namespace:
    """
    run(["kubectl", "create", "namespace", namespace], check=False)


def release_env(ctx: Context, env, dry_run=False):
    env_path = Path("envs") / env
    secrets = (env_path / "secrets").glob("*.yaml")

    for secret in sorted(secrets):
        # Sealed Secrets can't be validated like this
        # ctx.run(f"kubeval {secret}")
        if dry_run:
            logger.info(f"[DRY RUN] Applying {secret}")
            continue

        logger.info(f"Applying {secret}")
        run(["kubectl", "apply", "-f", secret])


def release(
    ctx,
    env,
    component=None,
    image=None,
    tag=None,
    replicas=None,
    dry_run=False,
    keep_configs=False,
    no_rollout_wait=False,
):
    tags: dict = {}
    images: dict = {}
    replica_counts: dict = {}
    components: List[str] = []

    if image:
        for i in image:
            k, v = i.split("=")
            images[k] = v

    if tag:
        for t in tag:
            k, v = t.split("=")
            tags[k] = v

    if replicas:
        for r in replicas:
            k, v = r.split("=")
            replica_counts[k] = v

    rel_id = generate_release_id()
    big_label(logger.info, f"Release {rel_id} to {env} environment starting")
    settings = load_env_settings(env)

    if component:
        components = component
    else:
        components = settings.COMPONENTS

    rel_path = RELEASE_TMP / rel_id

    logger.info("")
    logger.info("Releasing components:")
    for component in components:
        logger.info(f" - {component}")

    logger.info("")
    logger.info("Setting images and tags:")
    for path in components:
        tag = "(default)"
        image = "(default)"

        if path in tags:
            tag = tags[path]
        if path in images:
            image = images[path]

        logger.info(f" - {path} = {image}:{tag}")
    logger.info("")

    ensure_context(settings.KUBE_CONTEXT)
    ensure_namespace(settings.KUBE_NAMESPACE)
    release_env(ctx, env, dry_run)

    for path in components:
        logger.info("")
        label(logger.info, f"Releasing component {path}")

        component = Component(path)
        if path in images:
            component.image = images[path]
            del images[path]
        if path in tags:
            component.tag = tags[path]
            del images[tag]
        if path in replica_counts:
            component.replicas = replica_counts[path]
            del replica_counts[path]

        component.image_prefix = IMAGE_PREFIX
        component.namespace = settings.KUBE_NAMESPACE
        component.context = settings.KUBE_CONTEXT
        component.image_pull_secrets = settings.IMAGE_PULL_SECRETS

        component.patch_from_env(env)
        component.validate(ctx)

        component.release(ctx, rel_path, dry_run, no_rollout_wait)

    if images:
        logger.error("Unprocessed image configurations: ")
        for path in images:
            logger.error(f" - {path}={images[path]}")

    if tags:
        logger.error("Unprocessed tag configurations: ")
        for path in tags:
            logger.error(f" - {path}={tags[path]}")

    if replica_counts:
        logger.error("Unprocessed replica configurations: ")
        for path in replica_counts:
            logger.error(f" - {path}={replica_counts[path]}")

    if not keep_configs:
        logger.info(f"Removing temporary configurations from {rel_path}")
        rmtree(rel_path)
