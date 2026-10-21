@description('Location for the database.')
param location string

param tags object = {}

@description('Unique suffix for resource names.')
param resourceToken string

@description('The app identity, which reads and writes case files.')
param appPrincipalId string

@description('The developer, for running the desk locally against the same store. Empty skips it.')
param developerPrincipalId string = ''

// Built-in data-plane role "Cosmos DB Built-in Data Contributor".
var dataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: 'ruling-cosmos-${resourceToken}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: true // 1000 RU/s and 25 GB free, one account per subscription
    disableLocalAuth: true // identities only, no keys
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [{ locationName: location, failoverPriority: 0, isZoneRedundant: false }]
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: account
  name: 'ruling'
  properties: {
    resource: { id: 'ruling' }
    options: { throughput: 400 } // inside the free tier
  }
}

resource cases 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'cases'
  properties: {
    resource: {
      id: 'cases'
      partitionKey: { paths: ['/match_id'], kind: 'Hash' }
    }
  }
}

resource appAccess 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: account
  name: guid(account.id, appPrincipalId, dataContributorRoleId)
  properties: {
    roleDefinitionId: '${account.id}/sqlRoleDefinitions/${dataContributorRoleId}'
    principalId: appPrincipalId
    scope: account.id
  }
}

resource developerAccess 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (!empty(developerPrincipalId)) {
  parent: account
  name: guid(account.id, developerPrincipalId, dataContributorRoleId)
  properties: {
    roleDefinitionId: '${account.id}/sqlRoleDefinitions/${dataContributorRoleId}'
    principalId: developerPrincipalId
    scope: account.id
  }
}

output endpoint string = account.properties.documentEndpoint
output databaseName string = database.name
