# Cilium

## BGP Peering — Brocade ICX 6610 (Core01)

BGP peers with the Brocade core switch stack (Core01), NOT OPNsense.
The Brocade handles inter-VLAN routing for trusted VLANs — it needs the
routes to 192.168.69.0/24 so all VLANs can reach Kubernetes LoadBalancer IPs.

- **Cilium ASN:** 64514
- **Core01 ASN:** 64513
- **Peer address:** 192.168.42.4 (Brocade VIP on VLAN 42)
- **Advertised prefix:** 192.168.69.0/24 (LoadBalancer IPs)

### Brocade FastIron config (apply via ConsolePi or SSH)

```
configure terminal
router bgp
  local-as 64513
  neighbor k8s01 peer-group
  neighbor k8s01 remote-as 64514
  neighbor 192.168.42.51 peer-group k8s01
  neighbor 192.168.42.52 peer-group k8s01
  neighbor 192.168.42.53 peer-group k8s01
  neighbor 192.168.42.54 peer-group k8s01
  neighbor 192.168.42.55 peer-group k8s01
  neighbor 192.168.42.56 peer-group k8s01
  address-family ipv4 unicast
    neighbor k8s01 activate
  exit-address-family
exit
write memory
```

### Verify

```
show ip bgp summary
show ip bgp neighbors
show ip route bgp
```

Expected: 6 neighbors established, routes to 192.168.69.x/32 learned from each node.
