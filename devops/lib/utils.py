import importlib
import subprocess
from pathlib import Path
from typing import List
from time import time
import sys

from invoke import Context

from devops.lib.log import logger


class Settings:
    """
    Really, settings is a module, but don't tell anyone.
    """

    COMPONENTS: List[str]
    KUBE_CONTEXT: str
    KUBE_NAMESPACE: str
    IMAGE_PULL_SECRETS: dict


def get_changed_files(ctx: Context, modified=True, added=True, deleted=False):
    """
    Get changed files in working directory
    :param Context ctx:
    :param bool modified:
    :param bool added:
    :param bool deleted:
    :return list[str]:
    """
    if not (modified or added or deleted):
        raise NotImplementedError("What do you want to do?")

    opts = "-"
    if modified:
        opts += "m"
    if added:
        opts += "a"
    if deleted:
        opts += "r"

    result = ctx.run(f"hg status {opts}")

    files = [
        line.split(" ", 1)[1].strip()
        for line in result.stdout.replace("\r\n", "\n").split("\n")
        if line != ""
    ]

    return files


def load_env_settings(env: str) -> Settings:
    module = f"envs.{env}.settings"
    logger.info(f"Loading settings from {module}")
    return importlib.import_module(module)


def list_envs() -> List[str]:
    envs = []

    for path in Path("envs").iterdir():  # type: Path
        if path.is_dir() and not path.name.startswith("__"):
            envs.append(path.name)

    return envs


def run(
    args, cwd=None, check=True, env=None, stream=False
) -> subprocess.CompletedProcess:
    """
    Run a command

    :param List[str] args:
    :param str cwd:
    :param bool check:
    :param dict env:
    :param stream bool: If the output should be streamed instead of captured
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

    try:
        start = time()
        res = subprocess.run(args, **kwargs)
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
