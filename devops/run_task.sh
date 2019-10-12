#!/usr/bin/env sh

set -eu

. "devops/init-pyenv.sh"
. "$HOME/.poetry/env"

poetry install

echo poetry run invoke "$@"
poetry run invoke "$@"
