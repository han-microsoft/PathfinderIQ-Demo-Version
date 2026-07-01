#!/bin/sh
# nonce — mint a run id: <PREFIX>_<UTCstamp>. Default prefix RUN.
# Usage: nonce [PREFIX]
set -eu
prefix="${1:-RUN}"
printf '%s_%s\n' "$prefix" "$(date -u +%Y%m%d_%H%M%S)"
