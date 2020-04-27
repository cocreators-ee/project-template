import base64
import random
import string
from pathlib import Path
from shutil import rmtree
from typing import Iterable, List

import pytimeparse
import yaml
from invoke import Context
from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO
from ruamel.yaml.scalarstring import LiteralScalarString, PlainScalarString

from devops.lib.component import Component
from devops.lib.log import logger
from devops.lib.utils import (
    big_label,
    get_merged_kube_file,
    label,
    list_envs,
    load_env_settings,
    master_key_path,
    run,
    secrets_pem_path,
)
from devops.settings import KUBEVAL_SKIP_KINDS, UNSEALED_SECRETS_EXTENSION

TMP = Path("temp")


def generate_random_id() -> str:
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


def update_from_templates():
    envs = list_envs()

    rendered_files = []
    for env in envs:
        settings = load_env_settings(env)
        enabled_components = set(settings.COMPONENTS)

        components_in_filesystem = {
            p.parent.relative_to("envs", env, "merges").as_posix()
            for p in Path("envs", env, "merges").glob("**/kube")
        }
        components_in_filesystem |= {
            p.parent.relative_to("envs", env, "overrides").as_posix()
            for p in Path("envs", env, "overrides").glob("**/kube")
        }

        for path in enabled_components | components_in_filesystem:
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

    secrets = sorted(
        [
            secret_file
            for secret_file in (env_path / "secrets").glob("*.yaml")
            if not secret_file.name.endswith(UNSEALED_SECRETS_EXTENSION)
        ]
    )

    for secret in secrets:
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
    rollout_timeout=None,
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

    rel_id = generate_random_id()
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

    rel_path = TMP / rel_id

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

        if rollout_timeout:
            component.rollout_timeout = pytimeparse.parse(rollout_timeout)

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


def kubeval(keep_configs=False):
    """
    Check that all Kubernetes configs look valid with kubeval
    """

    label(logger.info, "Checking Kubernetes configs")

    def _should_ignore(path):
        if TMP in path.parents:
            return True

        return False

    merge_tmp = TMP / f"kubeval-{generate_random_id()}"

    kube_yamls = [
        str(get_merged_kube_file(path, merge_tmp))
        for path in Path(".").glob("**/kube/*.yaml")
        if not _should_ignore(path)
    ]

    skip_kinds = ",".join(KUBEVAL_SKIP_KINDS)

    run(["kubeval", "--strict", "--skip-kinds", skip_kinds] + kube_yamls)

    if not keep_configs and merge_tmp.exists():
        logger.info(f"Removing temporary kube merges from {merge_tmp}")
        rmtree(merge_tmp)
    if keep_configs and merge_tmp.exists():
        logger.info(f"Keeping temporary kube merges in {merge_tmp}")


def get_master_key(env: str, use_existing=True) -> Path:
    """
    Get the master key for SealedSecrets for the given env.

    :param str env: The environment
    :param bool use_existing: If set to True, tries to use existing key from filesystem
    instead of fetching a new one from the cluster.
    :return Path: The path to the master key
    """
    settings = load_env_settings(env)
    master_key_file = master_key_path(env=env)
    if use_existing and master_key_file.exists():
        return master_key_file

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

    logger.info(f"Saving master key to {master_key_file}")

    master_key_file.write_text(content, encoding="utf-8")
    return master_key_file


def unseal_secrets(env: str) -> None:
    """
    Decrypts the secrets for the desired env and base64 decodes them to make
    them easy to edit.

    :param str env: The environment.
    """
    # Validate env
    load_env_settings(env)

    master_key = get_master_key(env=env)
    secrets_pem = secrets_pem_path(env=env)

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

        content = kube_unseal(content, master_key, cert=secrets_pem)
        content = base64_decode_secrets(content)

        output_file.write_text(content, encoding="utf-8")


def seal_secrets(env: str, only_changed=False) -> None:
    """
    Base64 encodes and seals the secrets for the desired env.

    :param str env: The environment.
    :param bool only_changed: Reseal only changed secrets.
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
        sealed_content = kube_seal(content, cert=secrets_pem)

        if only_changed:
            master_key = get_master_key(env=env)
            sealed_original_content = output_file.read_text(encoding="utf-8")
            original_content = kube_unseal(
                sealed_original_content, master_key, cert=secrets_pem
            )
            sealed_content = _revert_unchanged_secrets(
                content, sealed_content, original_content, sealed_original_content
            )

        output_file.write_text(sealed_content, encoding="utf-8")


def _revert_unchanged_secrets(
    new_content: str,
    new_sealed_content: str,
    original_content: str,
    sealed_original_content: str,
) -> str:
    """
    Reverts the sealed version of each secrets to the original version if the actual
    value is unchanged in order to give nicer diffs.

    :param str new_content: The yaml document containing the new unsealed content.
    :param str new_sealed_content: The yaml document containing the new sealed content.
    :param str original_content: The yaml document containing the original unsealed
    content.
    :param str sealed_original_content: The yaml document containing the original sealed
    content.
    :return str: A sealed yaml document containing secrets from sealed_original_content
    and new_sealed_content.
    """
    new_content = yaml.safe_load(new_content)
    new_sealed_content = yaml.safe_load(new_sealed_content)
    original_content = yaml.safe_load(original_content)
    sealed_original_content = yaml.safe_load(sealed_original_content)

    for key, value in new_content["data"].items():
        if key in original_content["data"] and original_content["data"][key] == value:
            orig_value = sealed_original_content["spec"]["encryptedData"][key]
            new_sealed_content["spec"]["encryptedData"][key] = orig_value

    return yaml.safe_dump(new_sealed_content)


def base64_decode_secrets(content: str) -> str:
    """
    Base64 decode a Kubernetes Secret yaml file

    :param content: The content of the yaml file
    :return str: The base64 decoded version of the yaml file
    """
    ruamel_yaml = YAML()
    secrets = ruamel_yaml.load(content)

    data = secrets["data"]
    for key, value in data.items():
        if value is not None:
            value = base64.b64decode(value.encode("utf-8")).decode("utf-8")
            if "\n" in value:
                # If there's a line break in the value we want to dump it using
                # the literal syntax. This will use the pipe symbol (|) to
                # display for example PEM keys on multiple lines in the final
                # file rather than as one long string containing "\n".
                value = LiteralScalarString(value)
            data[key] = value

    stream = StringIO()
    ruamel_yaml.dump(secrets, stream)
    return stream.getvalue().rstrip() + "\n"


def base64_encode_secrets(content: str) -> str:
    """
    Base64 encode a Kubernetes Secret yaml file

    :return str: The readable version of the yaml file.
    """

    ruamel_yaml = YAML()
    secrets = ruamel_yaml.load(content)

    data = secrets["data"]
    for key, value in data.items():
        if value is not None:
            value = base64.b64encode(value.encode("utf-8")).decode("utf-8")
            data[key] = PlainScalarString(value)

    stream = StringIO()
    ruamel_yaml.dump(secrets, stream)
    return stream.getvalue().rstrip() + "\n"


def kube_unseal(content: str, master_key: Path, cert: Path) -> str:
    """
    Decrypt given content using kubeseal.

    :param str content: The content of the "SealedSecrets" yaml file.
    :param Path master_key: The private key to use for decryption.
    :param Path cert: Certificate / public key file to use for encryption.
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
            # Add the --cert flag to allow this to run also without a
            # ~/.kube/config file, for example in Travis.
            # For more details please see:
            # https://github.com/bitnami-labs/sealed-secrets/issues/341
            "--cert",
            cert,
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
