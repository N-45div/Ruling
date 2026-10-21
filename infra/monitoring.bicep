@description('Location for logs and traces.')
param location string

param tags object = {}

@description('Unique suffix for resource names.')
param resourceToken string

resource logs 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'ruling-logs-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// Agent Framework spans (agents, model calls, tools) land here through OpenTelemetry.
resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'ruling-insights-${resourceToken}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

output logsId string = logs.id
output logsCustomerId string = logs.properties.customerId
output insightsName string = insights.name
@secure()
output insightsConnectionString string = insights.properties.ConnectionString
