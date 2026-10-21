@description('Location for the Foundry resource.')
param location string

param tags object = {}

@description('Unique suffix for globally named resources.')
param resourceToken string

@description('Object ID of the developer to grant Foundry User on the resource. Empty skips the assignment.')
param principalId string = ''

@description('Object ID of the app identity, which calls the models in Azure. Empty skips the assignment.')
param appPrincipalId string = ''

@description('Tokens-per-minute capacity, in thousands, for the chat deployment.')
param chatCapacity int = 200

@description('Tokens-per-minute capacity, in thousands, for the embedding deployment.')
param embeddingCapacity int = 200

var accountName = 'ruling-ai-${resourceToken}'
// Built-in role "Foundry User": data-plane access to models and agents in the project.
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: accountName
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled'
    // Keyless: every caller authenticates with Entra ID.
    disableLocalAuth: true
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: 'ruling'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Ruling'
    description: 'Decision desk for refereeing calls.'
  }
}

// Child operations on one account conflict if they run in parallel, so the project,
// then each deployment, is created in turn.
resource chat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: 'gpt-5-mini'
  dependsOn: [project]
  sku: { name: 'GlobalStandard', capacity: chatCapacity }
  properties: {
    model: { format: 'OpenAI', name: 'gpt-5-mini', version: '2025-08-07' }
  }
}

resource embedding 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: 'text-embedding-3-small'
  dependsOn: [chat]
  sku: { name: 'GlobalStandard', capacity: embeddingCapacity }
  properties: {
    model: { format: 'OpenAI', name: 'text-embedding-3-small', version: '1' }
  }
}

resource developerAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(account.id, principalId, foundryUserRoleId)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
    principalId: principalId
    principalType: 'User'
  }
}

resource appAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(appPrincipalId)) {
  name: guid(account.id, appPrincipalId, foundryUserRoleId)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output accountName string = account.name
output accountEndpoint string = 'https://${accountName}.services.ai.azure.com'
output projectEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/${project.name}'
output chatDeployment string = chat.name
output embeddingDeployment string = embedding.name
