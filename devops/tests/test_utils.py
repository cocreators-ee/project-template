from devops.lib.utils import list_envs, load_env_settings, run


def test_load_env_settings():
    envs = list_envs()
    settings = load_env_settings(envs[0])
    _ = settings.IMAGE_PULL_SECRETS
    _ = settings.KUBE_CONTEXT
    _ = settings.KUBE_NAMESPACE
    _ = settings.COMPONENTS
    _ = settings.REPLICAS


def test_run():
    res = run(["python", "-c", "\"import sys; sys.stdout.write('test')\""])
    assert res.stdout == "test"

    res = run(["python", "-c", "\"import sys; sys.stderr.write('test')\""])
    assert res.stderr == "test"
