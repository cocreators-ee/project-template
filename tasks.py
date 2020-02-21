import json
import re
from contextlib import contextmanager
from os import environ
from pathlib import Path
from subprocess import CalledProcessError  # nosec
from time import sleep

from invoke import Context, task

import devops.settings
import devops.tasks
from devops.lib.log import logger
from devops.lib.utils import big_label, label, list_envs, load_env_settings, run

ALL_COMPONENTS = ["service/pipeline-agent"]

ENVS = list_envs()
LOCAL_ENV = "minikube"  # Determines some special rules

# Maximum number of Docker tags to keep after cleanup
MAX_TAGS = 50

validate_release_configs = task(devops.tasks.validate_release_configs)


@task(
    iterable=["component", "docker_arg"],
    help={
        "component": "The components to build - if none given defaults to: "
        + ", ".join(ALL_COMPONENTS),
        "dry_run": "Do not perform any changes, just generate configs and log what would be done",
        "docker_arg": "Arguments to pass to docker build, e.g. --docker-arg foo=bar "
        + "--docker-arg bar=baz",
    },
)
def build_images(ctx, component, dry_run=False, docker_arg=None):
    if not component:
        components = ALL_COMPONENTS
    else:
        components = [c.strip() for cs in component for c in cs.split(",")]

    if "DOCKER_HOST" not in environ:
        logger.warn(
            'DOCKER_HOST not set. You might want to run "minikube start" or run "minikube docker-env" and follow the instructions.'
        )

    with build_images_context(components, dry_run):
        devops.tasks.build_images(ctx, components, dry_run, docker_arg)


@contextmanager
def build_images_context(components, dry_run):
    """
    Context manager for building images.

    To be extended as needed, e.g. copy files to be visible for Dockerfile
    during the build and clean up them afterwards.

    :param list components: The components to be built.
    :param bool dry_run: True if it's a dry run.
    """

    # Setup
    try:
        yield
    finally:
        # Teardown
        pass


@task(
    iterable=["tag", "component", "image", "docker_arg"],
    help={
        "env": f"Environment to release, one of: {', '.join(ENVS)}",
        "component": "Components to release. Defaults to envs/<env>/settings.COMPONENTS",
        "replicas": "Override replicas in Kubernetes configs. --replicas <component>=<num>",
        "build": "Also build the components? Build has different defaults.",
        "image": "Override component Docker image, --image <component>=<image>",
        "tag": "Override component Docker tag, --tag <component>=<tag>",
        "dry_run": "Do not perform any changes, just generate configs and log what would be done",
        "keep_configs": "Do not delete generated configs after release",
        "no_rollout_wait": "Do not pause to wait for rollout completion, e.g. if updating release pipeline agents",
        "docker_arg": "Arguments to pass to docker build, e.g. --docker-arg foo=bar "
        + "--docker-arg bar=baz",
    },
)
def release(
    ctx,
    env,
    component=None,
    build=False,
    image=None,
    tag=None,
    replicas=None,
    dry_run=False,
    keep_configs=False,
    no_rollout_wait=False,
    docker_arg=None,
):
    if not component:
        components = ALL_COMPONENTS
    else:
        components = [c.strip() for cs in component for c in cs.split(",")]

    if build:
        build_images(ctx, components, dry_run, docker_arg)

    devops.tasks.release(
        ctx,
        env,
        components,
        image,
        tag,
        replicas,
        dry_run,
        keep_configs,
        no_rollout_wait,
    )


@task()
def init_kubernetes(ctx, env):
    """
    Initialize Kubernetes cluster
    :param Context ctx:
    :param str env:
    :return:
    """
    label(logger.info, f"Initializing Kubernetes for {env}")

    settings = load_env_settings(env)
    devops.tasks.ensure_context(settings.KUBE_CONTEXT)
    devops.tasks.ensure_namespace(settings.KUBE_NAMESPACE)

    def _get_kube_files(kube_context):
        kube_files = {f.name: f for f in Path("kube").glob("*.yaml")}

        overrides = (Path("kube") / kube_context / "overrides").glob("*.yaml")
        for f in overrides:
            kube_files[f.name] = f

        # Convert to sorted list
        kube_files = [kube_files[name] for name in sorted(kube_files.keys())]
        return kube_files

    def _apply(config, **kwargs):
        run(["kubectl", "apply", "-f", config], **kwargs)

    secrets = Path("envs") / env / "secrets.pem"
    if env == LOCAL_ENV:
        # Make sure local Sealed Secrets master key is applied first
        master_key = Path("envs") / env / "secrets.key"
        if master_key.exists():
            logger.info(f"Applying Sealed Secrets master key from {master_key}")
            _apply(master_key, check=False)

    for c in _get_kube_files(settings.KUBE_CONTEXT):
        _apply(c)

    # Wait for Sealed Secrets -controller to start up
    run(
        [
            "kubectl",
            "rollout",
            "status",
            "--namespace",
            "kube-system",
            "deploy/sealed-secrets-controller",
        ]
    )

    # And try to dump the signing cert
    logger.info("Trying to fetch Sealed Secrets signing cert")
    attempts = 5
    while True:
        try:
            res = run(["kubeseal", "--fetch-cert"])
        except CalledProcessError:
            attempts -= 1
            if attempts <= 0:
                raise Exception("Failed to fetch Sealed Secrets cert")

            sleep(2)
            continue

        with secrets.open("w") as dst:
            dst.write(res.stdout.decode("utf-8"))

        break

    if env == LOCAL_ENV:
        # Store master key if needed
        master_key = Path("envs") / env / "secrets.key"
        if not master_key.exists():
            logger.info("Trying to store Sealed Secrets master key")
            res = run(
                [
                    "kubectl",
                    "get",
                    "secret",
                    "--namespace",
                    "kube-system",
                    "-o",
                    "custom-columns=name:metadata.name",
                ]
            )
            secrets = []
            for line in res.stdout.decode("utf-8").splitlines():
                if line.startswith("sealed-secrets-key"):
                    secrets.append(line)

            with master_key.open("w") as dst:
                first = True
                for secret in secrets:
                    if not first:
                        dst.write("---\n")
                    first = False
                    res = run(
                        [
                            "kubectl",
                            "get",
                            "secret",
                            "--namespace",
                            "kube-system",
                            secret,
                            "-o",
                            "yaml",
                        ]
                    )
                    print(res.stdout)
                    dst.write(res.stdout.decode("utf-8") + "\n")


@task()
def init_hooks(ctx):
    """
    Initialize version control hooks
    :param Context ctx:
    """
    label(logger.info, "Installing pre-commit hooks")
    run(["pre-commit", "install"])


@task(pre=[init_hooks])
def init(ctx):
    """
    Initialize development environment
    :param Context ctx:
    """
    init_kubernetes(ctx, LOCAL_ENV)
    build_images(ctx)
    release(ctx, LOCAL_ENV)


@task()
def kubeval(ctx):
    """
    Check that all Kubernetes configs look valid with kubeval
    :param Context ctx:
    """

    label(logger.info, "Checking Kubernetes configs")

    def _should_ignore(path):
        parts = path.parts
        if parts[0] == "temp":
            return True
        elif parts[0] == "envs" and parts[2] == "merges":
            return True

        return False

    kube_yamls = [
        str(path)
        for path in Path(".").glob("**/kube/*.yaml")
        if not _should_ignore(path)
    ]

    skip_kinds = ",".join(devops.settings.KUBEVAL_SKIP_KINDS)

    run(["kubeval", "--skip-kinds", skip_kinds] + kube_yamls)


@task()
def update_from_templates(ctx):
    """
    Update kube yaml merges from templates
    :param Context ctx:
    """
    devops.tasks.update_from_templates(ctx)


@task()
def _update_from_templates_hook(ctx):
    """
    Update kube yaml merges from templates in a way that will work nicely with
    pre-commit hooks.

    :param Context ctx:
    """
    rendered_files = devops.tasks.update_from_templates(ctx)

    result = run(["git", "status", "--untracked-files=all", "-s"])
    untracked_files = result.stdout.decode(encoding="utf-8").split()
    statuses = untracked_files[0::2]
    files = untracked_files[1::2]
    # Mapping from file path to git short status
    untracked_files = {f: status for status, f in zip(statuses, files)}

    for f in rendered_files:
        if untracked_files.get(str(f)) == "??":
            raise ValueError(
                f"Rendered file {f} is untracked, use 'git add' to add it!"
            )


@task(pre=[_update_from_templates_hook, kubeval])
def pre_commit(ctx):
    """
    Local pre-commit hook
    :param Context ctx:
    """
    pass


@task()
def cleanup_acr_registry(ctx, registry):
    """
    Clean up a whole Azure Container Registry
    :param Context ctx:
    :param str registry: Name of the ACR, i.e. <name>.azurecr.io
    """
    big_label(logger.info, f"Cleaning up ACR registry {registry}")
    result = run(["az", "acr", "repository", "list", "--name", registry])
    repositories = json.loads(result.stdout)
    for repository in repositories:
        cleanup_acr_repository(ctx, registry, repository)


@task()
def cleanup_acr_repository(ctx, registry, repository):
    """
    Clean up a single repository in Azure Container Registry
    :param Context ctx:
    :param str registry:
    :param str repository:
    """
    label(logger.info, f"Cleaning up ACR {registry}/{repository} repository")
    result = run(
        [
            "az",
            "acr",
            "repository",
            "show-tags",
            "--name",
            registry,
            "--repository",
            repository,
        ]
    )
    tags = json.loads(result.stdout)

    # <branch>-<hash>-<YYYYMMDD>-<HHMMSS>
    tag_match = re.compile(r"^([^-]+)-([A-Za-z0-9]{7})-([0-9]+)-([0-9]+)$")

    def _sort_tag(key):
        """
        From <branch>-<hash>-<datetime> to <datetime>-<branch>-<hash>
        :param str key:
        :return str:
        """
        return re.sub(tag_match, "\\3-\\4-\\1-\\2", key)

    for tag in sorted(tags, key=_sort_tag)[MAX_TAGS:]:
        print(f"Deleting old tag {tag}")
        run(
            [
                "az",
                "acr",
                "repository",
                "delete",
                "--yes",
                "--name",
                registry,
                "--image",
                f"{repository}:{tag}",
            ]
        )


@task()
def get_master_key(ctx, env):
    """
    Get the master key for SealedSecrets for the given env.

    :param invoke.Context ctx: The invoke context.
    :param str env: The environment (one from /envs/)
    """
    devops.tasks.get_master_key(env=env)


@task()
def unseal_secrets(ctx, env):
    """Decrypts the secrets for the desired env and base64 decodes them to make
    them easy to edit.

    Examples:
    poetry run invoke secrets.unseal-secrets --env staging

    :param invoke.Context ctx: The invoke context.
    :param str env: The environment.
    """
    devops.tasks.unseal_secrets(env=env)


@task()
def seal_secrets(ctx, env):
    """Base64 encodes and seals the secrets for the desired env.

    Examples:
    poetry run invoke secrets.seal-secrets --env staging

    :param invoke.Context ctx: The invoke context.
    :param str env: The environment.
    """
    devops.tasks.seal_secrets(env=env)
