#!/usr/bin/env bash

mkdir /etc/named/named_config

cat > /etc/named/named.conf <<EOF
options {
  directory "/var/cache/bind";

  dnssec-validation yes;
  listen-on port 5053 { any; };
  listen-on-v6 { none; };
  recursion no;
  allow-query { any; };

  querylog no;

};
include "/etc/named/named_config/named.conf.local";

// use the default zones
include "/etc/bind/named.conf.default-zones";
EOF

cat > etc/named/named_config/named.conf.local <<EOF
options {
        ${NAMED_CONF_LOCAL}
};
EOF

cat > /etc/named/named_config/named.conf.local <<EOF
${LOCAL_LAN_ZONE}
EOF
