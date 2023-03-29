#!/bin/sh

etcdctl=/usr/local/bin/etcdctl

export ETCDCTL_CACERT='/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt'
export ETCDCTL_CERT='/var/lib/rancher/k3s/server/tls/etcd/server-client.crt'
export ETCDCTL_KEY='/var/lib/rancher/k3s/server/tls/etcd/server-client.key'
export ETCDCTL_API=3
unset ETCDCTL_ENDPOINTS

members=$($etcdctl member list|cut -d, -f 5|sed -e 's/ //g'|paste -sd ',')

$etcdctl endpoint status --endpoints=$members
$etcdctl defrag --endpoints=$members
$etcdctl endpoint status --endpoints=$members
