// ============================================================================
// Azure Storage Account — Shared blob containers (scenario-specific created at runtime)
// ============================================================================

@description('Name of the storage account (must be globally unique, lowercase, no hyphens)')
param name string

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

// ---------------------------------------------------------------------------
// Storage Account
// ---------------------------------------------------------------------------

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

// ---------------------------------------------------------------------------
// Blob Service & Shared Containers
// Scenario-specific containers are created at runtime by deploy_scenario.py.
// ---------------------------------------------------------------------------

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource networkDataContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'network-data'
  properties: {
    publicAccess: 'None'
  }
}

resource scenarioPackagesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'scenario-packages'
  properties: {
    publicAccess: 'None'
  }
}

resource publishReportsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'publish-reports'
  properties: {
    publicAccess: 'None'
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output id string = storageAccount.id
output name string = storageAccount.name
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
