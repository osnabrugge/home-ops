#!/bin/sh
set -eu

if grep -q '@@' /etc/nut/ups.conf; then
    echo "Refusing an unprovisioned UPS configuration" >&2
    exit 1
fi

# Server only: no upsmon, killpower hook, FSD, or driver shutdown invocation.
upsdrvctl -u nut start
exec upsd -F -u nut
