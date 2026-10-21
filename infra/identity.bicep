@description('Location for the identity.')
param location string

param tags object = {}

@description('Unique suffix for resource names.')
param resourceToken string

// The app's identity: created first so its roles exist before the app pulls its image.
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'ruling-app-${resourceToken}'
  location: location
  tags: tags
}

output id string = identity.id
output name string = identity.name
output principalId string = identity.properties.principalId
output clientId string = identity.properties.clientId
