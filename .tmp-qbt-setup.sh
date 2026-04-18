#!/bin/sh
# Login with temp password
curl -s -c /tmp/c "http://qbittorrent.default.svc.cluster.local/api/v2/auth/login" -d "username=admin&password=qfHzgTGc6"
echo ""

# Set password and all auth preferences
curl -s -b /tmp/c "http://qbittorrent.default.svc.cluster.local/api/v2/app/setPreferences" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode 'json={"web_ui_password":"Weren2qBhAdWupLVtwZlC449OOC3jj1Z","web_ui_csrf_protection_enabled":false,"web_ui_clickjacking_protection_enabled":false,"web_ui_host_header_validation_enabled":false,"web_ui_secure_cookie_enabled":false,"bypass_local_auth":true,"bypass_auth_subnet_whitelist_enabled":true,"bypass_auth_subnet_whitelist":"127.0.0.1/32\n10.0.0.0/8\n172.16.0.0/12\n192.168.0.0/16","web_ui_ban_duration":0,"web_ui_max_auth_fail_count":9999,"web_ui_reverse_proxy_enabled":true,"web_ui_reverse_proxies_list":"10.0.0.0/8,192.168.0.0/16"}'
echo ""

echo "=== Test unauthenticated ==="
curl -s http://qbittorrent.default.svc.cluster.local/api/v2/app/version
echo ""

echo "=== Test with new password ==="
curl -s -c /tmp/c2 "http://qbittorrent.default.svc.cluster.local/api/v2/auth/login" -d "username=admin&password=Weren2qBhAdWupLVtwZlC449OOC3jj1Z"
echo ""
curl -s -b /tmp/c2 http://qbittorrent.default.svc.cluster.local/api/v2/app/version
echo ""
