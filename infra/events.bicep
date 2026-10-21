@description('Location for the event hub.')
param location string

param tags object = {}

@description('Unique suffix for resource names.')
param resourceToken string

@description('The app identity, which publishes and reads the match feed.')
param appPrincipalId string

@description('The developer, for replaying a match from a laptop. Empty skips it.')
param developerPrincipalId string = ''

// Built-in role "Azure Event Hubs Data Owner": send and receive.
var dataOwnerRoleId = 'f526a384-b230-433a-b45c-95f59c4a2dec'

resource namespace 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: 'ruling-feed-${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Basic', tier: 'Basic', capacity: 1 }
  properties: {
    disableLocalAuth: true // identities only, no keys
    minimumTlsVersion: '1.2'
  }
}

// The live match feed: one event per on-ball action, restart, card and VAR check.
resource feed 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: namespace
  name: 'match-feed'
  properties: {
    partitionCount: 2
    messageRetentionInDays: 1
  }
}

resource appAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(namespace.id, appPrincipalId, dataOwnerRoleId)
  scope: namespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', dataOwnerRoleId)
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource developerAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(namespace.id, developerPrincipalId, dataOwnerRoleId)
  scope: namespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', dataOwnerRoleId)
    principalId: developerPrincipalId
    principalType: 'User'
  }
}

output namespace string = '${namespace.name}.servicebus.windows.net'
output hubName string = feed.name
