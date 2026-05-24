# kube-prometheus-stack

## NAS Deployments

### node-exporter

```yaml
services:
  node-exporter:
    container_name: node-exporter
    image: quay.io/prometheus/node-exporter
    restart: always
    network_mode: host
    ports:
      - '9100:9100'
    command:
      - '--path.rootfs=/host/root'
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--path.udev.data=/host/root/run/udev/data'
      - '--web.listen-address=0.0.0.0:9100'
      - '--collector.filesystem.mount-points-exclude=^/(rootfs/)?(dev|etc|host|proc|run|sys|volume1)($$|/)'
    volumes:
      - /:/host/root:ro
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
```

### smartctl-exporter

```yaml
services:
  smartctl-exporter:
    container_name: smartctl-exporter
    user: root
    image: quay.io/prometheuscommunity/smartctl-exporter
    restart: always
    privileged: true
    ports:
      - "9633:9633"
    command:
      - '--smartctl.device=/dev/nvme0'
      - '--smartctl.device=/dev/nvme1'
      - '--smartctl.device=/dev/sata1'
      - '--smartctl.device=/dev/sata2'
      - '--smartctl.device=/dev/sata3'
      - '--smartctl.device=/dev/sata4'
      - '--smartctl.device=/dev/sata5'
      - '--smartctl.device=/dev/sata6'
      - '--smartctl.device=/dev/sata7'
      - '--smartctl.device=/dev/sata8'
```
