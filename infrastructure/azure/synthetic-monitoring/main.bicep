// External synthetic monitoring for the homeops public surface.
//
// Runs Application Insights *standard* availability tests from Azure regions
// OUTSIDE the home network, validating the full public path
// (Cloudflare tunnel -> envoy-external -> app).
//
// COST: standard web tests bill PER EXECUTION and are the single largest line
// item in the subscription. 4 locations x 300s was 8,064 executions/day =
// $128/mo, which exhausted the monthly credit, disabled Key Vault and took ESO
// down with it. 2 locations x 900s is 1,344/day (-83%). Before raising either:
//   executions/day = count(endpoints) * (86400 / Frequency) * count(testLocations)
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
// EMPTIED 2026-08-23. These 7 tests cost $42.84 month-to-date (~$58/mo) on
// appi-homeops-synthetic — more than the entire $20-30/mo Azure budget, on a
// shared $210 cap whose exhaustion froze the subscription for a week. External
// uptime checking now belongs in a GitHub Actions cron, which is free on a
// public repo. Do not repopulate without doing the cost maths in the comment above.
param endpoints array = []
// Retired list, kept so the GitHub Actions replacement can reuse it:
//   echo.homeops.ca | status.homeops.ca | plex.homeops.ca/identity
//   home-assistant.homeops.ca | seerr.homeops.ca | kromgo.homeops.ca | auth.homeops.ca

@description('Azure test-runner locations (external vantage points). Each one multiplies cost.')
param testLocations array = [
  'us-il-ch1-azr'   // Central US (Chicago) - nearest external path to Toronto
  'emea-nl-ams-azr' // West Europe (Amsterdam) - true long-haul path
]

@description('How often each test runs, in seconds. Directly multiplies cost.')
param frequencySeconds int = 900

@description('Hard ceiling on daily ingestion. The credit-exhaustion incident had no cap at all.')
param dailyQuotaGb int = 1

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
    workspaceCapping: { dailyQuotaGb: dailyQuotaGb }
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
    // Defaults to 90d and is billed separately from the workspace's own 30d.
    RetentionInDays: 30
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
    Frequency: frequencySeconds
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
    // windowSize must span at least one run of every location, so it grows with
    // frequencySeconds or the window can legitimately contain no data.
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
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
