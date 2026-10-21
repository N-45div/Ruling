targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment, used to name the resource group and derive resource names.')
param environmentName string

@minLength(1)
@description('Primary location for all resources.')
param location string

@description('Object ID of the signed-in developer, granted access to the Foundry project and the case store.')
param principalId string = ''

var tags = { 'azd-env-name': environmentName }
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module identity 'identity.bicep' = {
  name: 'identity'
  scope: rg
  params: { location: location, tags: tags, resourceToken: resourceToken }
}

module foundry 'foundry.bicep' = {
  name: 'foundry'
  scope: rg
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    principalId: principalId
    appPrincipalId: identity.outputs.principalId
  }
}

module monitoring 'monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: { location: location, tags: tags, resourceToken: resourceToken }
}

module registry 'registry.bicep' = {
  name: 'registry'
  scope: rg
  params: { location: location, tags: tags, resourceToken: resourceToken, pullPrincipalId: identity.outputs.principalId }
}

module data 'data.bicep' = {
  name: 'data'
  scope: rg
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    appPrincipalId: identity.outputs.principalId
    developerPrincipalId: principalId
  }
}

module events 'events.bicep' = {
  name: 'events'
  scope: rg
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    appPrincipalId: identity.outputs.principalId
    developerPrincipalId: principalId
  }
}

module app 'app.bicep' = {
  name: 'app'
  scope: rg
  dependsOn: [registry, foundry, data, events]
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    identityId: identity.outputs.id
    identityClientId: identity.outputs.clientId
    registryLoginServer: registry.outputs.loginServer
    logsCustomerId: monitoring.outputs.logsCustomerId
    logsId: monitoring.outputs.logsId
    insightsConnectionString: monitoring.outputs.insightsConnectionString
    foundryProjectEndpoint: foundry.outputs.projectEndpoint
    chatModel: foundry.outputs.chatDeployment
    embeddingModel: foundry.outputs.embeddingDeployment
    cosmosEndpoint: data.outputs.endpoint
    cosmosDatabase: data.outputs.databaseName
    eventHubNamespace: events.outputs.namespace
    eventHubName: events.outputs.hubName
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output FOUNDRY_ACCOUNT_NAME string = foundry.outputs.accountName
output FOUNDRY_ENDPOINT string = foundry.outputs.accountEndpoint
output FOUNDRY_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output FOUNDRY_CHAT_MODEL string = foundry.outputs.chatDeployment
output FOUNDRY_EMBEDDING_MODEL string = foundry.outputs.embeddingDeployment
output COSMOS_ENDPOINT string = data.outputs.endpoint
output EVENTHUB_NAMESPACE string = events.outputs.namespace
output EVENTHUB_NAME string = events.outputs.hubName
output SERVICE_API_NAME string = app.outputs.name
output SERVICE_API_URI string = app.outputs.url
