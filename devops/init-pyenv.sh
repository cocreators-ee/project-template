#!/usr/bin/env sh

set -eu

# Set up pyenv
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

pyenv local 3.6.9
pyenv rehash
hash -r
