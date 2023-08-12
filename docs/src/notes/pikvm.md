# PiKVM

## Update PiKVM

```sh
rw; pacman -Syyu
reboot
```

## Load TESmart KVM

kvmd:
    gpio:
        drivers:
            tes:
                type: tesmart
                host: 192.168.10.10
                port: 5000
            wol_server0:
                type: wol
                mac: 98:fa:9b:62:2e:e9
            wol_server1:
                type: wol
                mac: 98:fa:9b:29:aa:5f
            wol_server2:
                type: wol
                mac: 98:fa:9b:2f:ee:1f
            wol_server3:
                type: wol
                mac: 38:f3:ab:c8:85:4b
            wol_server4:
                type: wol
                mac: f8:75:a4:fe:34:bb
            wol_server5:
                type: wol
                mac: 1c:69:7a:01:40:f0
            wol_server6:
                type: wol
                mac: 98:fa:9b:62:2e:e9
            wol_server7:
                type: wol
                mac: 98:fa:9b:29:aa:5f
            wol_server8:
                type: wol
                mac: 98:fa:9b:62:2e:e9
            wol_server9:
                type: wol
                mac: 98:fa:9b:29:aa:5f
            wol_server10:
                type: wol
                mac: 98:fa:9b:2f:ee:1f
            wol_server11:
                type: wol
                mac: 38:f3:ab:c8:85:4b
            wol_server12:
                type: wol
                mac: f8:75:a4:fe:34:bb
            wol_server13:
                type: wol
                mac: 1c:69:7a:01:40:f0
            wol_server14:
                type: wol
                mac: 00:00:00:00:00:00
            wol_server15:
                type: wol
                mac: 00:e0:67:27:40:0e
        scheme:
            wol_server0:
                driver: wol_server0
                pin: 0
                mode: output
                switch: false
            wol_server1:
                driver: wol_server1
                pin: 0
                mode: output
                switch: false
            wol_server2:
                driver: wol_server2
                pin: 0
                mode: output
                switch: false
            wol_server3:
                driver: wol_server3
                pin: 0
                mode: output
                switch: false
            wol_server4:
                driver: wol_server4
                pin: 0
                mode: output
                switch: false
            wol_server5:
                driver: wol_server5
                pin: 0
                mode: output
                switch: false
            wol_server6:
                driver: wol_server6
                pin: 0
                mode: output
                switch: false
            wol_server7:
                driver: wol_server7
                pin: 0
                mode: output
                switch: false
            wol_server8:
                driver: wol_server8
                pin: 0
                mode: output
                switch: false
            wol_server9:
                driver: wol_server9
                pin: 0
                mode: output
                switch: false
            wol_server10:
                driver: wol_server10
                pin: 0
                mode: output
                switch: false
            wol_server11:
                driver: wol_server11
                pin: 0
                mode: output
                switch: false
            wol_server12:
                driver: wol_server12
                pin: 0
                mode: output
                switch: false
            wol_server13:
                driver: wol_server13
                pin: 0
                mode: output
                switch: false
            wol_server14:
                driver: wol_server14
                pin: 0
                mode: output
                switch: false
            wol_server15:
                driver: wol_server15
                pin: 0
                mode: output
                switch: false
            server0_led:
                driver: tes
                pin: 0
                mode: input
            server0_switch:
                driver: tes
                pin: 0
                mode: output
                switch: false
            server1_led:
                driver: tes
                pin: 1
                mode: input
            server1_switch:
                driver: tes
                pin: 1
                mode: output
                switch: false
            server2_led:
                driver: tes
                pin: 2
                mode: input
            server2_switch:
                driver: tes
                pin: 2
                mode: output
                switch: false
            server3_led:
                driver: tes
                pin: 3
                mode: input
            server3_switch:
                driver: tes
                pin: 3
                mode: output
                switch: false
            server4_led:
                driver: tes
                pin: 4
                mode: input
            server4_switch:
                driver: tes
                pin: 4
                mode: output
                switch: false
            server5_led:
                driver: tes
                pin: 5
                mode: input
            server5_switch:
                driver: tes
                pin: 5
                mode: output
                switch: false
            server6_led:
                driver: tes
                pin: 6
                mode: input
            server6_switch:
                driver: tes
                pin: 6
                mode: output
                switch: false
            server7_led:
                driver: tes
                pin: 7
                mode: input
            server7_switch:
                driver: tes
                pin: 7
                mode: output
                switch: false
            server8_led:
                driver: tes
                pin: 8
                mode: input
            server8_switch:
                driver: tes
                pin: 8
                mode: output
                switch: false
            server9_led:
                driver: tes
                pin: 9
                mode: input
            server9_switch:
                driver: tes
                pin: 9
                mode: output
                switch: false
            server10_led:
                driver: tes
                pin: 10
                mode: input
            server10_switch:
                driver: tes
                pin: 10
                mode: output
                switch: false
            server11_led:
                driver: tes
                pin: 11
                mode: input
            server11_switch:
                driver: tes
                pin: 11
                mode: output
                switch: false
            server12_led:
                driver: tes
                pin: 12
                mode: input
            server12_switch:
                driver: tes
                pin: 12
                mode: output
                switch: false
            server13_led:
                driver: tes
                pin: 13
                mode: input
            server13_switch:
                driver: tes
                pin: 13
                mode: output
                switch: false
            server14_led:
                driver: tes
                pin: 14
                mode: input
            server14_switch:
                driver: tes
                pin: 14
                mode: output
                switch: false
            server15_led:
                driver: tes
                pin: 15
                mode: input
            server15_switch:
                driver: tes
                pin: 15
                mode: output
                switch: false

        view:
            table:
                - ["TESMART Switch"]
                - []
                - ["#PVE01", server0_led, server0_switch|Switch, "wol_server0|Send Wake-on-LAN"]
                - ["#PI01", server1_led, server1_switch|Switch, "wol_server1|Send Wake-on-LAN"]
                - ["#PI02", server2_led, server2_switch|Switch, "wol_server2|Send Wake-on-LAN"]
                - ["#K3S01", server3_led, server4_switch|Switch, "wol_server3|Send Wake-on-LAN"]
                - ["#K3S02", server4_led, server4_switch|Switch, "wol_server4|Send Wake-on-LAN"]
                - ["#K3S03", server5_led, server5_switch|Switch, "wol_server5|Send Wake-on-LAN"]
                - ["#K3S04", server6_led, server6_switch|Switch, "wol_server6|Send Wake-on-LAN"]
                - ["#K3S05", server7_led, server7_switch|Switch, "wol_server7|Send Wake-on-LAN"]
                - ["#K3S06", server8_led, server8_switch|Switch, "wol_server8|Send Wake-on-LAN"]
                - ["#K3S07", server9_led, server9_switch|Switch, "wol_server9|Send Wake-on-LAN"]
                - ["#K3S08", server10_led, server10_switch|Switch, "wol_server10|Send Wake-on-LAN"]
                - ["#K3S09", server11_led, server11_switch|Switch, "wol_server11|Send Wake-on-LAN"]
                - ["#K3S10", server12_led, server12_switch|Switch, "wol_server12|Send Wake-on-LAN"]

    atx:
        type: disabled

2. Restart kvmd
    ```sh
    systemctl restart kvmd.service
    ```

## Load Custom EDID

1. Add or replace the file `/etc/kvmd/tc358743-edid.hex`
    ```text
    00FFFFFFFFFFFF0052628888008888881C150103800000780AEE91A3544C99260F505425400001000100010001000100010001010101D32C80A070381A403020350040442100001E7E1D00A0500019403020370080001000001E000000FC0050492D4B564D20566964656F0A000000FD00323D0F2E0F000000000000000001C402030400DE0D20A03058122030203400F0B400000018E01500A04000163030203400000000000018B41400A050D011203020350080D810000018AB22A0A050841A3030203600B00E1100001800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000045
    ```

2. Restart kvmd
    ```sh
    systemctl restart kvmd.service
    ```

## Disable SSL

1. Add or replace the file `/etc/kvmd/nginx/nginx.conf`
    ```nginx
    worker_processes 4;

    error_log stderr;

    include /usr/share/kvmd/extras/*/nginx.ctx-main.conf;

    events {
        worker_connections 1024;
        use epoll;
        multi_accept on;
    }

    http {
        types_hash_max_size 4096;
        server_names_hash_bucket_size 128;

        access_log off;

        include /etc/kvmd/nginx/mime-types.conf;
        default_type application/octet-stream;
        charset utf-8;

        sendfile on;
        tcp_nodelay on;
        tcp_nopush on;
        keepalive_timeout 10;
        client_max_body_size 4k;

        client_body_temp_path    /tmp/kvmd-nginx/client_body_temp;
        fastcgi_temp_path        /tmp/kvmd-nginx/fastcgi_temp;
        proxy_temp_path            /tmp/kvmd-nginx/proxy_temp;
        scgi_temp_path            /tmp/kvmd-nginx/scgi_temp;
        uwsgi_temp_path            /tmp/kvmd-nginx/uwsgi_temp;

        include /etc/kvmd/nginx/kvmd.ctx-http.conf;
        include /usr/share/kvmd/extras/*/nginx.ctx-http.conf;

        server {
            listen 80;
            listen [::]:80;
            server_name localhost;
            include /etc/kvmd/nginx/kvmd.ctx-server.conf;
            include /usr/share/kvmd/extras/*/nginx.ctx-server.conf;
        }
    }
    ```

2. Restart kvmd-nginx
    ```sh
    systemctl restart kvmd-nginx.service
    ```

## Monitoring

### Disable auth on prometheus exporter

```sh
rw
nano /usr/lib/python3.11/site-packages/kvmd/apps/kvmd/api/export.py
# Add the False arg on the exposed_http decorator...
# @exposed_http("GET", "/export/prometheus/metrics", False)
ro
systemctl restart kvmd.service
```

### Install node-exporter

```sh
pacman -S prometheus-node-exporter
systemctl enable --now prometheus-node-exporter
```

### Install promtail

1. Install promtail
    ```sh
    pacman -S promtail
    systemctl enable promtail
    ```

2. Override the promtail systemd service
    ```sh
    mkdir -p /etc/systemd/system/promtail.service.d/
    cat >/etc/systemd/system/promtail.service.d/override.conf <<EOL
    [Service]
    Type=simple
    ExecStart=
    ExecStart=/usr/bin/promtail -config.file /etc/loki/promtail.yaml
    EOL
    ```

3. Add or replace the file `/etc/loki/promtail.yaml`
    ```yaml
    server:
      log_level: info
      disable: true

    client:
      url: "https://loki.devbu.io/loki/api/v1/push"

    positions:
      filename: /tmp/positions.yaml

    scrape_configs:
      - job_name: journal
        journal:
          path: /run/log/journal
          max_age: 12h
          labels:
            job: systemd-journal
        relabel_configs:
          - source_labels: ["__journal__systemd_unit"]
            target_label: unit
          - source_labels: ["__journal__hostname"]
            target_label: hostname
    ```

4. Start promtail
    ```sh
    systemctl daemon-reload
    systemctl start promtail.service
    ```
