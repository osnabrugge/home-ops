<div align="center">

<img src="https://camo.githubusercontent.com/5b298bf6b0596795602bd771c5bddbb963e83e0f/68747470733a2f2f692e696d6775722e636f6d2f7031527a586a512e706e67" align="center" width="144px" height="144px"/>

### My home operations repository

_... managed with Flux, Renovate and GitHub Actions_ 🤖

[![Kubernetes](https://img.shields.io/badge/v1.27-blue?style=for-the-badge&logo=kubernetes&logoColor=white)](https://k3s.io/)
[![Renovate](https://img.shields.io/github/actions/workflow/status/osnabrugge/home-ops/renovate.yaml?branch=main&label=&logo=renovatebot&style=for-the-badge&color=blue)](https://github.com/osnabrugge/home-ops/actions/workflows/renovate.yaml)

[![Discord](https://img.shields.io/discord/673534664354430999?color=blue&style=for-the-badge&logo=discord)](https://discord.gg/M9xtHc9A "k8s at home Discord Community")
[![Home-Internet](https://img.shields.io/uptimerobot/status/m792892408-a2f5ebd5a54fff87945cd162?color=brightgreeen&label=Home%20Internet&style=for-the-badge&logo=pfSense&logoColor=white)](https://stats.uptimerobot.com/wvKDmHvrpQ)

</div>

---

## 📗Overview

Semi-hyperconverged [k3s](https://k3s.io/) GitOps managed cluster.

## Cluster Components

- [actions-runner-controller](https://github.com/actions/actions-runner-controller) runs GitHub Actions as self-hosted runners on this cluster.
- [authelia](https://www.authelia.com/) provides single-sign-on and multifactor authentication.
- [calico](https://www.tigera.io/project-calico/) CNI providing networking between pods, services and exposes services via BGP and multipath.
- [cert-manager](https://cert-manager.io/) requests SSL certificates, both self-signed and from [let's encrypt](https://letsencrypt.org/) and stores them as Kubernetes resources.
- [external-dns](https://github.com/kubernetes-sigs/external-dns) publishes DNS records to [cloudflare](https://www.cloudflare.com/) only from explicitly annotated ingress objects.  An additional instance publishes all ingresses and services to internal [pi-hole](https://pi-hole.net/) servers which automates split domain routing.
- [external-secrets](https://external-secrets.io/) provides secret management between this cluster's resources and those stored in [azure keyvault](https://azure.microsoft.com/en-us/products/key-vault/).
- [flux](https://toolkit.fluxcd.io/) GitOps operator that keeps this cluster in sync with this Git repository.
- [ingress-nginx](https://kubernetes.github.io/ingress-nginx/) ingress controller that publishes web apps through a HTTP reverse proxy from Kubernetes ingresses.
- [multus](https://github.com/k8snetworkplumbingwg/multus-cni) enables pods access to seperate VLANs and/or physical networks with [whereabouts](https://github.com/k8snetworkplumbingwg/whereabouts) to ensure consistent IP addressing across physical nodes (Rook Ceph requirement if storage and host traffic are to be separated).
- [rook-ceph](https://github.com/rook/rook) manages a ceph cluster that provides replicated persistent storage.
- [volsync](https://github.com/backube/volsync) and [snapscheduler](https://github.com/backube/snapscheduler) enable restic backup and recovery of persistent volume claims to [azure blob storage](https://azure.microsoft.com/en-us/products/storage/blobs).

Additional applications include [hajimari](https://github.com/toboshii/hajimari), [error-pages](https://github.com/tarampampam/error-pages), [echo-server](https://github.com/Ealenn/Echo-Server), [system-upgrade-controller](https://github.com/rancher/system-upgrade-controller), [reloader](https://github.com/stakater/Reloader), [kured](https://github.com/weaveworks/kured) and more.

## 🤝 Thanks

A lot of inspiration for my cluster came from the people that have shared their clusters over at [awesome-home-kubernetes](https://github.com/k8s-at-home/awesome-home-kubernetes).  A few in particular deserve a ton of recognition for their hardwork, talent and help to the community:

- [angelnu/k8s-gitops](https://github.com/angelnu/k8s-gitops)
- [billimek/k8s-gitops](https://github.com/billimek/k8s-gitops)
- [bjw-s/k8s-gitops](https://github.com/bjw-s/k8s-gitops)
- [carpenike/k8s-gitops](https://github.com/carpenike/k8s-gitops)
- [onedr0p/home-ops](https://github.com/onedr0p/home-ops)
