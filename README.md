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

- [actions-runner-controller](https://github.com/actions/actions-runner-controller) - Self-hosted Github runners.
- [authelia](https://www.authelia.com/) - Provides single-sign-on and multifactor authentication
- [calico](https://www.tigera.io/project-calico/) - Container networking interface for inter pod and service networking
- [cert-manager](https://cert-manager.io/) - Operator to request SSL certificates and store them as Kubernetes resources
- [external-dns](https://github.com/kubernetes-sigs/external-dns) - Operator to publish DNS records to Cloudflare (and other providers) based on Kubernetes ingresses
- [external-secrets](https://external-secrets.io/) - Operator for secret management with [azure keyvault](https://azure.microsoft.com/en-us/products/key-vault/)
- [flux](https://toolkit.fluxcd.io/) - GitOps operator for managing Kubernetes clusters from a Git repository
- [ingress-nginx](https://kubernetes.github.io/ingress-nginx/) - Kubernetes ingress controller used for a HTTP reverse proxy of Kubernetes ingresses
- [k8s_gateway](https://github.com/ori-edge/k8s_gateway) - DNS resolver that provides local DNS to your Kubernetes ingresses
- [kopia](https://kopia.io/) - Provides snapshot backups leveraging [kyverno](https://kyverno.io/) for policies to apply cronjobs on PVCs
- [metallb](https://metallb.universe.tf/) - Load balancer for Kubernetes services
- [multus](https://github.com/k8snetworkplumbingwg/multus-cni) - Enables multiple interfaces for pods to access my storage network and [whereabouts](https://github.com/k8snetworkplumbingwg/whereabouts) to ensure consistent IP addressing across physical nodes
- [rook-ceph](https://github.com/rook/rook) - Provision persistent replicated storage with Kubernetes
- [volsync](https://github.com/backube/volsync) and [snapscheduler](https://github.com/backube/snapscheduler) enable restic backup and recovery of persistent volume claims to Azure Blob Storage.

Additional applications include [hajimari](https://github.com/toboshii/hajimari), [error-pages](https://github.com/tarampampam/error-pages), [echo-server](https://github.com/Ealenn/Echo-Server), [system-upgrade-controller](https://github.com/rancher/system-upgrade-controller), [reloader](https://github.com/stakater/Reloader), [kured](https://github.com/weaveworks/kured) and more

## 🤝 Thanks

A lot of inspiration for my cluster came from the people that have shared their clusters over at [awesome-home-kubernetes](https://github.com/k8s-at-home/awesome-home-kubernetes)

- [angelnu/k8s-gitops](https://github.com/angelnu/k8s-gitops)
- [billimek/k8s-gitops](https://github.com/billimek/k8s-gitops)
- [bjw-s/k8s-gitops](https://github.com/bjw-s/k8s-gitops)
- [carpenike/k8s-gitops](https://github.com/carpenike/k8s-gitops)
- [onedr0p/home-ops](https://github.com/onedr0p/home-ops)
