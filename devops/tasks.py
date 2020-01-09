import base64
import random
import string
from pathlib import Path
from shutil import rmtree
from typing import List

from devops.lib.component import Component
from devops.lib.log import logger
from devops.lib.utils import (
    big_label,
    label,
    list_envs,
    load_env_settings,
    master_key_path,
    run,
    secrets_pem_path,
)
from devops.settings import UNSEALED_SECRETS_EXTENSION
from invoke import Context
from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO
from ruamel.yaml.scalarstring import LiteralScalarString, PlainScalarString

RELEASE_TMP = Path("temp")


def generate_release_id() -> str:
    length = 5
    chars = string.ascii_lowercase + string.digits

    return "".join(random.choice(chars) for _ in range(length))  # nosec


def build_images(ctx, components, dry_run=False, docker_args=None):
    big_label(
        logger.info,
        f"Building images{f' with args: {docker_args}' if docker_args else ''}",
    )
    for c in components:
        component = Component(c)
        component.build(ctx, dry_run, docker_args)


def update_from_templates(ctx):
    envs = list_envs()

    rendered_files = []
    for env in envs:
        settings = load_env_settings(env)
        components = settings.COMPONENTS

        for path in components:
            component = Component(path)
            rendered_files.extend(component.render_templates(env, settings))

    return rendered_files


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

    old_secrets = (env_path / "secrets" / "obsolete").glob("*.yaml")
    for secret in sorted(old_secrets, reverse=True):
        if dry_run:
            logger.info(f"[DRY RUN] Deleting {secret}")
            continue

        logger.info(f"Deleting {secret}")
        run(["kubectl", "delete", "-f", secret])


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
            path, value = i.split("=")
            images[path] = value

    if tag:
        for t in tag:
            path, value = t.split("=")
            tags[path] = value

    if replicas:
        for r in replicas:
            path, value = r.split("=")
            replica_counts[path] = value

    rel_id = generate_release_id()
    big_label(logger.info, f"Release {rel_id} to {env} environment starting")
    settings = load_env_settings(env)

    if component:
        components = component
    else:
        components = settings.COMPONENTS

    # Override env settings for replicas
    if replica_counts:
        for path in replica_counts:
            settings.REPLICAS[path] = replica_counts[path]

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
            images.pop(path)
        if path in tags:
            component.tag = tags[path]
            tags.pop(path)
        if path in settings.REPLICAS:
            component.replicas = settings.REPLICAS[path]
            replica_counts.pop(path, None)

        component.namespace = settings.KUBE_NAMESPACE
        component.context = settings.KUBE_CONTEXT
        component.image_pull_secrets = settings.IMAGE_PULL_SECRETS

        component.patch_from_env(env)
        component.validate(ctx)

        component.release(ctx, rel_path, dry_run, no_rollout_wait)

    if images:
        logger.error("Unprocessed image configurations:")
        for path in images:
            logger.error(f" - {path}={images[path]}")

    if tags:
        logger.error("Unprocessed tag configurations:")
        for path in tags:
            logger.error(f" - {path}={tags[path]}")

    if replica_counts:
        logger.error("Unprocessed replica configurations:")
        for path in replica_counts:
            logger.error(f" - {path}={replica_counts[path]}")

    if not keep_configs:
        logger.info(f"Removing temporary configurations from {rel_path}")
        if rel_path.exists():
            rmtree(rel_path)


def get_master_key(env: str) -> None:
    """
    Get the master key for SealedSecrets for the given env.

    :param str env: The environment
    """
    settings = load_env_settings(env)
    ensure_context(settings.KUBE_CONTEXT)

    label(logger.info, f"Getting master key for {env}")

    # Based on:
    # https://github.com/bitnami-labs/sealed-secrets#how-can-i-do-a-backup-of-my-sealedsecrets
    result = run(
        [
            "kubectl",
            "get",
            "secret",
            "-n",
            "kube-system",
            "-l",
            "sealedsecrets.bitnami.com/sealed-secrets-key",
            "-o",
            "yaml",
        ]
    )

    content = result.stdout.decode(encoding="utf-8")
    output_file = master_key_path(env=env)

    logger.info(f"Saving master key to {output_file}")

    output_file.write_text(content, encoding="utf-8")


def unseal_secrets(env: str) -> None:
    """
    Decrypts the secrets for the desired env and base64 decodes them to make
    them easy to edit.

    :param str env: The environment.
    """
    # Validate env
    load_env_settings(env)

    master_key = master_key_path(env=env)
    if not master_key.exists():
        get_master_key(env=env)

    sealed_secret_files = [
        secret_file
        for secret_file in (Path("envs") / env / "secrets").glob("*.yaml")
        if not secret_file.name.endswith(UNSEALED_SECRETS_EXTENSION)
    ]

    label(logger.info, f"Unsealing secrets for {env}")

    for input_file in sealed_secret_files:
        output_file = input_file.with_name(input_file.stem + UNSEALED_SECRETS_EXTENSION)

        logger.info(f"Unsealing {input_file} to {output_file}")

        content = input_file.read_text(encoding="utf-8")

        content = kube_unseal(content, master_key)
        content = base64_decode_secrets(content)

        output_file.write_text(content, encoding="utf-8")


def seal_secrets(env: str) -> None:
    """
    Base64 encodes and seals the secrets for the desired env.

    :param str env: The environment.
    """
    # Validate env
    load_env_settings(env)

    secrets_pem = secrets_pem_path(env=env)

    unsealed_secret_files = (Path("envs") / env / "secrets").glob(
        f"*{UNSEALED_SECRETS_EXTENSION}"
    )

    label(logger.info, f"Sealing secrets for {env}")

    for input_file in unsealed_secret_files:
        output_file_name = input_file.name[: -len(UNSEALED_SECRETS_EXTENSION)] + ".yaml"
        output_file = input_file.with_name(output_file_name)

        logger.info(f"Sealing {input_file} as {output_file}")

        content = input_file.read_text(encoding="utf-8")

        content = base64_encode_secrets(content)
        content = kube_seal(content, cert=secrets_pem)

        output_file.write_text(content, encoding="utf-8")


def base64_decode_secrets(content: str) -> str:
    """
    Base64 decode a Kubernetes Secret yaml file

    :param content: The content of the yaml file
    :return str: The base64 decoded version of the yaml file
    """
    yaml = YAML()
    secrets = yaml.load(content)

    data = secrets["data"]
    for key, value in data.items():
        if value is not None:
            value = base64.b64decode(value.encode("utf-8")).decode("utf-8")
            if "\n" in value:
                # If there's a line break in the value we want to dump it using
                # the literal syntax
                value = LiteralScalarString(value)
            data[key] = value

    stream = StringIO()
    yaml.dump(secrets, stream)
    return stream.getvalue().rstrip() + "\n"


def base64_encode_secrets(content: str) -> str:
    """
    Base64 encode a Kubernetes Secret yaml file

    :return str: The readable version of the yaml file.
    """

    yaml = YAML()
    secrets = yaml.load(content)

    data = secrets["data"]
    for key, value in data.items():
        if value is not None:
            value = base64.b64encode(value.encode("utf-8")).decode("utf-8")
            data[key] = PlainScalarString(value)

    stream = StringIO()
    yaml.dump(secrets, stream)
    return stream.getvalue().rstrip() + "\n"


def kube_unseal(content: str, master_key: Path) -> str:
    """
    Decrypt given content using kubeseal.

    :param str content: The content of the "SealedSecrets" yaml file.
    :param Path master_key: The private key to use for decryption.
    :return str: The content of a Kubernetes "Secrets" yaml file.
    """
    result = run(
        [
            "kubeseal",
            "--recovery-unseal",
            "--recovery-private-key",
            master_key,
            "-o",
            "yaml",
        ],
        input=content.encode(encoding="utf-8"),
    )

    return result.stdout.decode(encoding="utf-8")


def kube_seal(content: str, cert: Path) -> str:
    """
    Encrypt given content using kubeseal.

    :param str content: The content of a Kubernetes "Secrets" yaml file.
    :param Path cert: Certificate / public key file to use for encryption.
    :return str: The content of the "SealedSecrets" yaml file.
    """
    result = run(
        ["kubeseal", "--cert", cert, "-o", "yaml"],
        input=content.encode(encoding="utf-8"),
    )

    return result.stdout.decode(encoding="utf-8").rstrip() + "\n"
