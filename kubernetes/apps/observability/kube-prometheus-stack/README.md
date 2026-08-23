# kube-prometheus-stack

## nas01 deployment

### node-exporter

```yaml
services:
  node-exporter:
    command:
      - '--path.rootfs=/host/root'
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--path.udev.data=/host/root/run/udev/data'
      - '--web.listen-address=0.0.0.0:9100'
      - >-
        --collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)
    image: >-
      ghcr.io/prometheus/node-exporter:v1.12.1@sha256:1b4e4438faca4dd7e001dd445d161a4a2091b0fededa84093b3a8dfeae1f1be0
    ports:
      - '9100:9100'
    restart: always
    volumes:
      - /:/host/root:ro
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
```

### smartctl-exporter

```yaml
services:
  smartctl-exporter:
    image: >-
      quay.io/prometheuscommunity/smartctl-exporter:0.14.0@sha256:cfe22c36d7d2fac48ebf619707305acb65eb0fb670656eb80f356e606d782bc1
    ports:
      - '9633:9633'
    privileged: True
    restart: always
    user: root
```

## nas02 deployment

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


