#!/bin/sh
# Set up and run Smriti (family, elder and care-team apps).
cd "$(dirname "$0")" && exec python3 start.py "$@"
