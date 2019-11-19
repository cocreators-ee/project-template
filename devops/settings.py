from os import environ

LOG_FORMAT = environ.get(
    "LOG_FORMAT", "%(asctime)s (%(process)d) [%(levelname)8s]: %(message)s"
)

# Prefix for all docker images built in this project, e.g. `project-`
IMAGE_PREFIX = "myproj-"

LOG_LEVEL = "INFO"

TEMPLATE_HEADER = """#
# THIS FILE HAS BEEN AUTOMATICALLY GENERATED FROM {file}
# DO NOT MODIFY THIS FILE BY HAND, INSTEAD RUN: poetry run invoke update-from-templates
#
"""

try:
    from devops.settings_local import *
except ImportError:
    pass
