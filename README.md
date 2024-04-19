<div align="center">

<img src="https://raw.githubusercontent.com/onedr0p/home-ops/main/docs/src/assets/logo.png" align="center" width="144px" height="144px"/>

### My home operations repository

_... managed with Flux, Renovate and GitHub Actions_ 🤖

[![Kubernetes](https://img.shields.io/badge/v1.27-blue?style=for-the-badge&logo=kubernetes&logoColor=white)](https://k3s.io/)
[![Renovate](https://img.shields.io/github/actions/workflow/status/osnabrugge/home-ops/renovate.yaml?branch=main&label=&logo=renovatebot&style=for-the-badge&color=blue)](https://github.com/osnabrugge/home-ops/actions/workflows/renovate.yaml)

[![Discord](https://img.shields.io/discord/673534664354430999?color=blue&style=for-the-badge&logo=discord)](https://discord.gg/M9xtHc9A "k8s at home Discord Community")
[![Home-Internet](https://img.shields.io/uptimerobot/status/m792892408-a2f5ebd5a54fff87945cd162?color=brightgreeen&label=Home%20Internet&style=for-the-badge&logo=opnSense&logoColor=white)](https://stats.uptimerobot.com/wvKDmHvrpQ)

</div>

---

## 📗Overview

This repo is the sources of truth for a semi-hyperconverged [k3s](https://k3s.io/) cluster that I maintain at home.  To best of my ability, I've tried to document the cluster's configuration and the tools I use to manage it.  I hope that it can serve as a reference for others who are interested in building their own cluster.

## Cluster Components

- Authentication
    - [authelia](https://www.authelia.com/) provides single-sign-on and multifactor authentication
    - [cert-manager](https://cert-manager.io/) requests and manages SSL certificates, both self-signed and from [let's encrypt](https://letsencrypt.org/)
    - [external-secrets](https://external-secrets.io/) provides secret management using:
        - [azure workload identity](https://azure.github.io/azure-workload-identity/docs/) delegates token issuance to this cluster
        - [azure keyvault](https://azure.microsoft.com/en-us/products/key-vault/) is the storage backend for secrets
- Networking
    - [cilium](https://cilium.io/) CNI providing networking between pods, services and provides L2 loadbalancing
    - [ingress-nginx](https://kubernetes.github.io/ingress-nginx/) for reverse proxy ingress and loadbalancing
    - [multus](https://github.com/k8snetworkplumbingwg/multus-cni) enables pods to access seperate VLANs & physical networks using:
        - [sr-iov plugin](https://github.com/k8snetworkplumbingwg/sriov-network-device-plugin) attach pods to sr-iov capable interfaces & applicable VFs
        - [whereabouts](https://github.com/k8snetworkplumbingwg/whereabouts) to ensure consistent IP addressing across physical nodes
- Storage
  - [openebs](https://github.com/openebs/openebs) provides ephemeral storage for pods
  - [rook-ceph](https://github.com/rook/rook) manages a ceph cluster that provides replicated persistent storage
  - [azure blob storage](https://azure.microsoft.com/en-us/products/storage/blobs) cold storage for backups and volume snapshots
- Cluster Management
    - [actions-runner-controller](https://github.com/actions/actions-runner-controller) runs GitHub Actions as self-hosted runners on this cluster
    - [flux](https://toolkit.fluxcd.io/) GitOps operator that keeps this cluster in sync with this repository
- DNS Management
    - [external-dns](https://github.com/kubernetes-sigs/external-dns) publishes DNS records and automates split-horizon DNS between:
        - [cloudflare](https://www.cloudflare.com/) for explicitly annotated ingress objects
        - [pi-hole](https://pi-hole.net/) for all servies and ingress objects
- Backup
    - [volsync](https://github.com/backube/volsync) and [snapscheduler](https://github.com/backube/snapscheduler) enable restic backup and recovery of persistent volume claims to














## 🤝 Thanks

A lot of inspiration for my cluster came from the members of the [Home Operations Discord ](https://discord.gg/home-operations) community.  They are responsible for these great resources:

- [Flux Cluster Template](https://github.com/onedr0p/flux-cluster-template) is a community driven template that provides a great starting point for anyone who has limited knowledge of Kubernetes and GitOps
- [Kubsearch.dev](https://kubesearch.dev//) is a search engine for apps deployed across the community's clusters. It's a great way to find inspiration or solve challenges for your own cluster

Specifc thanks to the following members for their contributions and where I drew inspiration from:

- [angelnu/k8s-gitops](https://github.com/angelnu/k8s-gitops)
- [billimek/k8s-gitops](https://github.com/billimek/k8s-gitops)
- [bjw-s/k8s-gitops](https://github.com/bjw-s/k8s-gitops)
- [carpenike/k8s-gitops](https://github.com/carpenike/k8s-gitops)
- [onedr0p/home-ops](https://github.com/onedr0p/home-ops)
