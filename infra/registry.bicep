@description('Location for the registry.')
param location string

param tags object = {}

@description('Unique suffix for resource names.')
param resourceToken string

@description('Principal that may pull images: the app identity.')
param pullPrincipalId string

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

// Images are built inside the registry (azd remote build), so no local Docker is needed.
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'rulingacr${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, pullPrincipalId, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: pullPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output name string = registry.name
output loginServer string = registry.properties.loginServer
