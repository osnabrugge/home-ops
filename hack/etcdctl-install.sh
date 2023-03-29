#!/usr/bin/env bash

set -eux

etcd_version=v3.5.3

case "$(uname -m)" in
    aarch64) arch="arm64" ;;
    x86_64) arch="amd64" ;;
esac;

etcd_name="etcd-${etcd_version}-linux-${arch}"

curl -sSfL "https://github.com/etcd-io/etcd/releases/download/${etcd_version}/${etcd_name}.tar.gz" \
    | tar xzvf - -C /usr/local/bin --strip-components=1 "${etcd_name}/etcdctl"

etcdctl version
