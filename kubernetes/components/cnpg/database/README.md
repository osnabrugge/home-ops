# Shared-cluster database component

Creates one app-owned `Database` resource in the existing `postgres16` cluster.
The shared Cluster still owns roles, passwords and database backups.

Include this component from an application's database Kustomization, target the
`database` namespace, and set the required Flux substitution `CNPG_DATABASE` to
the existing database/resource/role name. Changing that value is an identity
change, not a routine refactor.

This component does not create or upgrade a Cluster, move data, or issue new
credentials. Multi-database applications such as NetBox Diode keep their explicit
resources rather than split ownership solely to reuse this single-database helper.
Kustomize's origin annotation points at the shared source; resource identity and
the complete Database spec must remain unchanged when adopting the component.
