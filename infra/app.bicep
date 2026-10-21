@description('Location for the app.')
param location string

param tags object = {}

@description('Unique suffix for resource names.')
param resourceToken string

param identityId string
param identityClientId string
param registryLoginServer string
param logsCustomerId string
param logsId string
@secure()
param insightsConnectionString string
param foundryProjectEndpoint string
param chatModel string
param embeddingModel string
param cosmosEndpoint string
param cosmosDatabase string
param eventHubNamespace string
param eventHubName string

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'ruling-env-${resourceToken}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logsCustomerId
        sharedKey: listKeys(logsId, '2022-10-01').primarySharedKey
      }
    }
  }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ruling-api'
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [{ server: registryLoginServer, identity: identityId }]
      secrets: [{ name: 'insights', value: insightsConnectionString }]
    }
    template: {
      containers: [
        {
          name: 'api'
          // Placeholder until `azd deploy` builds and pushes the real image.
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'AZURE_CLIENT_ID', value: identityClientId }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'FOUNDRY_CHAT_MODEL', value: chatModel }
            { name: 'FOUNDRY_EMBEDDING_MODEL', value: embeddingModel }
            { name: 'COSMOS_ENDPOINT', value: cosmosEndpoint }
            { name: 'COSMOS_DATABASE', value: cosmosDatabase }
            { name: 'EVENTHUB_NAMESPACE', value: eventHubNamespace }
            { name: 'EVENTHUB_NAME', value: eventHubName }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'insights' }
          ]
        }
      ]
      // One replica: checks waiting for human approval live in memory, and judges never hit a cold start.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

output name string = api.name
output url string = 'https://${api.properties.configuration.ingress.fqdn}'
