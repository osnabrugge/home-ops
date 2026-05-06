# Torrent Ecosystem Implementation Summary

**Date:** May 5, 2026
**Status:** Infrastructure committed, private credentials and cautious activation still pending

## Summary

The torrent stack has been wired into the cluster with the supporting applications needed for client control, release monitoring, IRC connectivity, indexer management, and library automation.

The repository now treats this stack as infrastructure only. Tracker-identifying details, account status, and private operational notes should not be committed here.

## Components In Scope

- qBittorrent
- autobrr
- thelounge
- prowlarr
- sonarr
- radarr
- qui

## What Was Implemented

- application manifests and supporting config for the torrent stack
- ExternalSecret wiring for app credentials
- documentation for app-secret setup and staged activation
- cluster-local API and UI integration points between the services

## What Still Requires Manual Input

- Azure Key Vault secret values for each app
- manual private indexer configuration in prowlarr
- manual IRC network configuration in thelounge
- validation of safe download and seeding behavior before broader automation is enabled

## Secret Management Convention

This repository uses one Azure Key Vault secret per app or service where possible. ExternalSecrets then extract the full object into a Kubernetes Secret for that app.

See [docs/TRACKER-CREDENTIALS-SETUP.md](/home/sean/projects/talos/home-ops/docs/TRACKER-CREDENTIALS-SETUP.md) for the current documented pattern.

## Operational Note

If you need tracker-specific URLs, rules, account reminders, or ratio recovery notes, keep them in a private system outside the repository.
