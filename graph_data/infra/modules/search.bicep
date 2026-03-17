// ============================================================================
// Azure AI Search — Service with system-assigned managed identity
// ============================================================================

@description('Name of the AI Search resource')
param name string

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

@description('SKU for the search service')
@allowed(['free', 'basic', 'standard', 'standard2', 'standard3'])
param skuName string = 'standard'

// ---------------------------------------------------------------------------
// AI Search Service
// ---------------------------------------------------------------------------

resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'Default'
    publicNetworkAccess: 'Enabled'
    semanticSearch: 'free'
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output id string = search.id
output name string = search.name
output endpoint string = 'https://${search.name}.search.windows.net'
output principalId string = search.identity.principalId
