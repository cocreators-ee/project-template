import importlib
import subprocess  # nosec
from pathlib import Path
from time import time
from typing import List, Optional

from devops.lib.log import logger


class Settings:
    """
    Really, settings is a module, but don't tell anyone.
    """

    COMPONENTS: List[str]
    KUBE_CONTEXT: str
    KUBE_NAMESPACE: str
    IMAGE_PULL_SECRETS: Optional[dict]
    REPLICAS: Optional[dict]


def load_env_settings(env: str) -> Settings:
    module = f"envs.{env}.settings"
    logger.info(f"Loading settings from {module}")
    settings = importlib.import_module(module)

    # Set some defaults for optional values
    settings.IMAGE_PULL_SECRETS = getattr(settings, "IMAGE_PULL_SECRETS", {})
    settings.REPLICAS = getattr(settings, "REPLICAS", {})

    return settings


def list_envs() -> List[str]:
    envs = []

    for path in Path("envs").iterdir():  # type: Path
        if path.is_dir() and not path.name.startswith("__"):
            envs.append(path.name)

    return envs


def run(
    args, cwd=None, check=True, env=None, stream=False, timeout=None
) -> subprocess.CompletedProcess:
    """
    Run a command

    :param List[str] args:
    :param str cwd:
    :param bool check:
    :param dict env:
    :param stream bool: If the output should be streamed instead of captured
    :param float timeout: Seconds to wait before failing
    :raises subprocess.CalledProcessError:
    :raises subprocess.TimeoutExpired:
    :return subprocess.CompletedProcess:
    """
    # Convert Paths to strings
    for index, value in enumerate(args):
        args[index] = str(value)
    logger.info("  " + " ".join(args))

    kwargs = {"cwd": cwd, "check": check, "env": env}

    if not stream:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE

    if timeout:
        kwargs["timeout"] = timeout

    try:
        start = time()
        res = subprocess.run(args, **kwargs)  # nosec
        end = time()
        logger.info(f"  ✔ ... done in {end - start:.3f}s")

        return res
    except subprocess.CalledProcessError as e:
        logger.error("Failed to run" + " ".join(args))
        if e.stdout:
            logger.error("----- STDOUT -----")
            logger.error(e.stdout.decode("utf-8"))
        if e.stderr:
            logger.error("----- STDERR -----")
            logger.error(e.stderr.decode("utf-8"))
        if e.stdout or e.stderr:
            logger.error("------------------")
        raise


def label(fn, text: str):
    l = len(text)
    fill = "-" * l

    fn(f"/-{fill}-\\")
    fn(f"| {text} |")
    fn(f"\\-{fill}-/")


def big_label(fn, text: str):
    l = len(text)
    fill = "-" * l
    padd = " " * l

    fn("")
    fn(f"/---{fill}---\\")
    fn(f"|   {padd}   |")
    fn(f"|   {text}   |")
    fn(f"|   {padd}   |")
    fn(f"\\---{fill}---/")
    fn("")
