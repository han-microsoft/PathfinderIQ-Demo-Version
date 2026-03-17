// ============================================================================
// Azure AI Foundry — Foundry resource + Project (CognitiveServices-based)
// Replaces the old Hub/Project (MachineLearningServices) architecture to
// unlock gpt-4 family models in Agent Service.
// ============================================================================

@description('Name of the AI Foundry resource (CognitiveServices account)')
param foundryName string

@description('Name of the AI Foundry Project')
param projectName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

// Connected resources
@description('Resource ID of the AI Search service')
param aiSearchId string

@description('Name of the AI Search service')
param aiSearchName string

@description('Resource ID of the Storage account')
param storageAccountId string

@description('Name of the Storage account')
param storageAccountName string

@description('Name of the blob container for runbooks')
param storageContainerName string

@description('GPT model capacity in 1K TPM units (e.g. 10 = 10K tokens/min)')
param gptCapacity int = 1000

// ---------------------------------------------------------------------------
// AI Foundry Resource (CognitiveServices account, kind=AIServices)
// This is a superset of Azure OpenAI — hosts models AND enables projects.
// ---------------------------------------------------------------------------

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: foundryName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: foundryName
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
  }
}

// ---------------------------------------------------------------------------
// Model Deployment — text-embedding-3-small
// ---------------------------------------------------------------------------

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundry
  name: 'text-embedding-3-small'
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-small'
      version: '1'
    }
  }
}

// ---------------------------------------------------------------------------
// Model Deployment — gpt-5.2
// ---------------------------------------------------------------------------

resource gpt52deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-09-01' = {
  parent: foundry
  name: 'gpt-5.2'
  dependsOn: [embeddingDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: gptCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.2'
      version: '2025-12-11'
    }
  }
}

// resource gpt41Deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-09-01' = {
//   parent: foundry
//   name: 'gpt-4.1'
//   dependsOn: [embeddingDeployment]
//   sku: {
//     name: 'GlobalStandard'
//     capacity: gptCapacity
//   }
//   properties: {
//     model: {
//       format: 'OpenAI'
//       name: 'gpt-4.1'
//       version: '2025-04-14'
//     }
//   }
// }

// ---------------------------------------------------------------------------
// Connection — AI Search (on the Foundry resource)
// ---------------------------------------------------------------------------

resource searchConnection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  parent: foundry
  name: 'aisearch-connection'
  properties: {
    authType: 'AAD'
    category: 'CognitiveSearch'
    target: 'https://${aiSearchName}.search.windows.net'
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ApiVersion: '2025-05-01'
      ResourceId: aiSearchId
    }
  }
}

// ---------------------------------------------------------------------------
// Connection — Azure Blob Storage (for Agent Service file search / runbooks)
// ---------------------------------------------------------------------------

resource storageConnection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  parent: foundry
  name: 'storage-connection'
  properties: {
    authType: 'AAD'
    category: 'AzureBlob'
    target: 'https://${storageAccountName}.blob.${environment().suffixes.storage}'
    isSharedToAll: true
    metadata: {
      AccountName: storageAccountName
      ContainerName: storageContainerName
      ResourceId: storageAccountId
    }
  }
}

// ---------------------------------------------------------------------------
// AI Foundry Project (child of the Foundry resource)
// ---------------------------------------------------------------------------

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: 'AI Foundry Project for the Autonomous Network NOC demo'
    displayName: 'Autonomous Network NOC Project'
  }
}

// ---------------------------------------------------------------------------
// Capability Hosts — required to initialise the Agent Service data plane.
// Without these, the project exists in ARM but the SDK returns 404
// "Project not found" for all agent / assistant operations.
//
// Using 2025-04-01-preview: the caphost auto-configures its own storage,
// vector, and thread backends. The 2025-06-01 GA API requires explicit
// connection arrays with strict category validation that is unreliable.
// ---------------------------------------------------------------------------

resource accountCapabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-04-01-preview' = {
  name: '${foundryName}-caphost'
  parent: foundry
  properties: {
    capabilityHostKind: 'Agents'
  }
  dependsOn: [
    project
  ]
}

resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = {
  name: '${projectName}-caphost'
  parent: project
  properties: {
    aiServicesConnections: []
    storageConnections: []
    threadStorageConnections: []
    vectorStoreConnections: []
  }
  dependsOn: [
    accountCapabilityHost
  ]
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output foundryId string = foundry.id
output foundryName string = foundry.name
output foundryEndpoint string = foundry.properties.endpoint
output foundryPrincipalId string = foundry.identity.principalId
output projectName string = project.name
// The AI Projects SDK requires the services.ai.azure.com hostname (not
// cognitiveservices.azure.com) with the /api/projects/<name> path.
output projectEndpoint string = 'https://${foundryName}.services.ai.azure.com/api/projects/${project.name}'
