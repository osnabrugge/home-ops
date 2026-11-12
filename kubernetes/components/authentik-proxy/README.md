# Private infrastructure UI proxy

This component creates an app-owned, operator-managed Authentik proxy application
and its cross-namespace Service reference grant. Native blueprints must not also
own those application/provider/binding objects.

Required Flux substitutions:

- `AUTHENTIK_APP`: unique lowercase application slug.
- `AUTHENTIK_TITLE`: display name.
- `AUTHENTIK_HOST`: existing private HTTPS hostname, without a scheme.
- `AUTHENTIK_BACKEND_NAMESPACE`, `AUTHENTIK_BACKEND_SERVICE`,
  `AUTHENTIK_BACKEND_PORT`: existing HTTP Service destination.

The consumer identity Kustomization targets namespace `auth`. Access is limited
to the existing administrator group and declared infrastructure owner; no
directory membership or backend authorization is changed.

This does not create an HTTPRoute or NetworkPolicy. Provision and verify the
provider first, then explicitly connect the consumer's private route and protect
its UI ingress. Preserve known cluster Service clients and any independent boot,
syslog, webhook or machine-authentication contract. An SSO redirect is not a
backend-health check or a completed human login.

Do not use this component in front of PrintStash's paired-device API or another
application with a verified native OIDC/SAML integration. Changes affect every
consumer; currently the Hubble, netboot.xyz, Prometheus, Alertmanager and
VictoriaLogs UI identities use it.
