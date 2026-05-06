# Torrent Ecosystem Optimization Guide

**Last Updated:** May 5, 2026
**Priority:** Conservative activation and sustained seeding health

## Intent

This guide describes safe operating principles for the torrent stack without publishing tracker-identifying details or account-specific status.

## Operating Principles

1. Prefer stable seeding over aggressive intake.
2. Do not expand automation until upload behavior is verified.
3. Keep long seed times and avoid premature cleanup.
4. Use manual approval or narrow filters for risky or unknown feeds.
5. Keep tracker-specific policies and credentials out of Git.

## Recommended qBittorrent Baseline

Use settings that bias toward retention and conservative throughput:
- long or unlimited seed time
- a non-trivial max seeding ratio before removal or stop
- modest concurrent download limits
- moderate active torrent limits
- categories aligned with downstream automation

Any exact values should be tuned privately based on your tracker obligations and actual upload performance.

## Recommended Activation Order

1. Verify qBittorrent is healthy and existing torrents can seed.
2. Verify autobrr can reach qBittorrent.
3. Add indexers in prowlarr and test them manually.
4. Add IRC networks in thelounge only if needed for your workflow.
5. Connect sonarr and radarr after the client and indexers are stable.
6. Enable automation gradually and review results before widening scope.

## Verification Focus

Track the following privately while bringing the system online:
- overall seeding health
- hold-or-remove exposure
- upload consistency
- storage stability
- tracker-side account standing

## What Not To Publish

Do not commit:
- tracker names
- tracker URLs
- IRC hosts and channels
- API keys, passkeys, authkeys, or tokens
- account ratios or warnings
- donor status or dispute history

## Cross-References

- [docs/TRACKER-CREDENTIALS-SETUP.md](/home/sean/projects/talos/home-ops/docs/TRACKER-CREDENTIALS-SETUP.md)
- [docs/TORRENT-SETUP-ACTION-PLAN.md](/home/sean/projects/talos/home-ops/docs/TORRENT-SETUP-ACTION-PLAN.md)
