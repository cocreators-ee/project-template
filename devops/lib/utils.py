import importlib
import subprocess  # nosec
import types
from copy import deepcopy
from io import StringIO
from pathlib import Path
from time import time
from typing import Callable, List, Optional, Union

import yaml
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
    :param bool stream: If the output should be streamed instead of captured
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

    start = time()
    try:
        res = subprocess.run(args, **kwargs)  # nosec
    except subprocess.CalledProcessError as e:
        logger.error("Failed to run " + " ".join(args))
        log_subprocess_output(e, logger.error)
        logger.error(f"  ✘ ... failed in {time() - start:.3f}s")
        raise
    else:
        log_subprocess_output(res, logger.debug)
        logger.info(f"  ✔ ... done in {time() - start:.3f}s")
        return res


def log_subprocess_output(
    res: Union[subprocess.CompletedProcess, subprocess.CalledProcessError],
    log: Callable,
):
    if res.stdout:
        log("  ----- STDOUT -----")
        log(res.stdout.decode("utf-8").strip())
    if res.stderr:
        log("  ----- STDERR -----")
        log(res.stderr.decode("utf-8").strip())
    if res.stdout or res.stderr:
        log("  ------------------")


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


def merge_docs(src: List[dict], overrides: List[dict]):
    """
    Merges Yaml documents.

    You need to load the src documents using yaml.Loader and overrides with
    yaml.BaseLoader for this to work properly.

    :param src:
    :param overrides:
    :return dict: New dictionary of merged values
    """
    docs = deepcopy(src)

    # Yaml "FullLoader" that can parse all the values to their normal types in Python
    loader = yaml.Loader(StringIO(""))

    def _basevalue_to_value(value: str, path: str):
        """
        Parse string values such as `5` to the expected Python types
        :param str value: Value to parse
        :param str path: For debugging, path in the yaml tree
        :return: Parsed value
        """
        tag = loader.resolve(yaml.ScalarNode, value, (True, False))
        node = yaml.ScalarNode(tag, value)
        resolved = loader.construct_object(node, True)

        #  if resolved != value:
        #    print(f"{path} {type(value)}: {value} -> {type(resolved)}: {resolved}")

        return resolved

    def _merge_part(doc, overrides, path=""):
        """
        Merge the trees - recursive part of logic
        """

        def _nest(_doc, _overrides, _path):
            """
            Support nesting even when original doc ran out of matching data
            """
            if _doc is None:
                _doc = type(_overrides)()

            return _merge_part(_doc, _overrides, _path)

        if type(doc) == dict:
            res = {}
            for key in overrides:
                if overrides[key] == "~":
                    # Remove these from target
                    pass
                elif overrides[key] == "":
                    # Use original value
                    res[key] = doc[key]
                elif type(overrides[key]) in (str, int, bool, float, complex):
                    # Simply overridden values
                    res[key] = _basevalue_to_value(overrides[key], path)
                elif key not in doc:
                    # Added values
                    res[key] = _nest(None, overrides[key], f"{path}.{key}")
                else:
                    # Nesting
                    res[key] = _nest(doc[key], overrides[key], f"{path}.{key}")

                # Remove all overridden values from source doc so we can later just
                # copy the remaining values over
                if key in doc:
                    del doc[key]

            for key in doc:
                res[key] = doc[key]

            return res
        elif type(doc) == list:
            res = []
            for idx, value_override in enumerate(overrides):
                if idx > len(doc) - 1:
                    # Added values
                    if isinstance(value_override, types.GeneratorType):
                        res.append(_nest(None, value_override, f"{path}[{idx}]"))
                    else:
                        res.append(value_override)
                    continue

                value = doc[idx]
                if value_override == "~":
                    # Remove these from target
                    continue
                elif value_override == "":
                    # Use original value
                    res.append(value)
                elif type(value_override) in (str, int, bool, float, complex):
                    # Simply overridden values
                    res.append(_basevalue_to_value(value_override, path))
                else:
                    res.append(_nest(value, value_override, f"{path}[{idx}]"))

            if len(doc) > len(overrides):
                for item in doc[len(overrides) :]:
                    res.append(item)

            return res
        else:
            raise NotImplementedError(f"Dunno how to merge {type(doc)}")

    for i, doc in enumerate(docs):
        docs[i] = _merge_part(doc, overrides[i])

    return docs
