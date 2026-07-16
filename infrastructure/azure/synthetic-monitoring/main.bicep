// External synthetic monitoring for the homeops public surface.
//
// Runs Application Insights *standard* availability tests from Azure regions
// OUTSIDE the home network, validating the full public path
// (Cloudflare tunnel -> envoy-external -> app) every 5 minutes.
//
// Deploy:
//   az deployment group create -g rg-homeops-prod \
//     -f infrastructure/azure/synthetic-monitoring/main.bicep
//
// This lives in the empty rg-homeops-prod and gives a live green/red dashboard
// plus availability alerts. Notification wiring is via the action group below.

@description('Azure region for the workspace + App Insights (metadata only; tests run from the locations list).')
param location string = resourceGroup().location

@description('Public endpoints to probe from outside. Each becomes a standard availability test.')
param endpoints array = [
  { name: 'echo', url: 'https://echo.homeops.ca', expectedStatus: 200 }
  { name: 'status', url: 'https://status.homeops.ca', expectedStatus: 200 }
  { name: 'plex', url: 'https://plex.homeops.ca/identity', expectedStatus: 200 }
  { name: 'home-assistant', url: 'https://home-assistant.homeops.ca', expectedStatus: 200 }
  { name: 'seerr', url: 'https://seerr.homeops.ca', expectedStatus: 200 }
  { name: 'kromgo', url: 'https://kromgo.homeops.ca', expectedStatus: 200 }
  { name: 'auth', url: 'https://auth.homeops.ca', expectedStatus: 200 }
]

@description('Azure test-runner locations (external vantage points). Geographically diverse.')
param testLocations array = [
  'us-va-ash-azr'   // East US (Virginia)
  'us-il-ch1-azr'   // Central US (Chicago)
  'us-ca-sjc-azr'   // West US (San Jose)
  'emea-nl-ams-azr' // West Europe (Amsterdam)
]

@description('How many test locations must report failure before the test is marked failed.')
param failedLocationCount int = 2

var workspaceName = 'log-homeops-synthetic'
var appInsightsName = 'appi-homeops-synthetic'
var actionGroupName = 'ag-homeops-synthetic'

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    features: { enableLogAccessUsingOnlyResourcePermissions: true }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// Action group. Pushover is not a native Azure receiver, so we expose a webhook
// receiver that a translator (Cloudflare Worker / Logic App) can forward to
// Pushover. Update webhookUri after the translator is deployed, or add an
// emailReceivers entry for a quick start.
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: actionGroupName
  location: 'global'
  properties: {
    groupShortName: 'homeops'
    enabled: true
    // Placeholder — no receivers wired yet. Availability data + portal alerts
    // still work; add emailReceivers or a webhook to get pushed notifications.
    emailReceivers: []
    webhookReceivers: []
  }
}

resource webTests 'Microsoft.Insights/webtests@2022-06-15' = [for ep in endpoints: {
  name: 'wt-homeops-${ep.name}'
  location: location
  tags: {
    'hidden-link:${appInsights.id}': 'Resource'
  }
  kind: 'standard'
  properties: {
    SyntheticMonitorId: 'wt-homeops-${ep.name}'
    Name: 'homeops ${ep.name} (external)'
    Enabled: true
    Frequency: 300
    Timeout: 30
    Kind: 'standard'
    RetryEnabled: true
    Locations: [for loc in testLocations: { Id: loc }]
    Request: {
      RequestUrl: ep.url
      HttpVerb: 'GET'
      ParseDependentRequests: false
    }
    ValidationRules: {
      ExpectedHttpStatusCode: ep.expectedStatus
      SSLCheck: true
      SSLCertRemainingLifetimeCheck: 7
    }
  }
}]

resource availabilityAlerts 'Microsoft.Insights/metricAlerts@2018-03-01' = [for (ep, i) in endpoints: {
  name: 'alert-homeops-${ep.name}-availability'
  location: 'global'
  properties: {
    description: 'External availability of ${ep.url} dropped below 100% (probed from outside the network).'
    severity: 2
    enabled: true
    scopes: [ webTests[i].id, appInsights.id ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria'
      webTestId: webTests[i].id
      componentId: appInsights.id
      failedLocationCount: failedLocationCount
    }
    actions: [ { actionGroupId: actionGroup.id } ]
  }
}]

output appInsightsName string = appInsights.name
output appInsightsResourceId string = appInsights.id
output actionGroupId string = actionGroup.id
output testCount int = length(endpoints)
