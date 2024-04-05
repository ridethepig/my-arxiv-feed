#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
$SCRIPT_DIR/.venv/bin/python arxiv.py -c "sys" --strict --onlynew --translate-title