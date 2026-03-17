// ============================================================================
// Graph Data Provisioner — Main Orchestrator
// Subscription-scoped deployment that creates the resource group and
// supporting Azure resources for AI Search data provisioning.
//
// No apps, no Cosmos DB, no VNet, no containers — just the backing
// services needed to populate AI Search indexes and storage.
// ============================================================================

targetScope = 'subscription'

// ---------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------

@minLength(1)
@maxLength(64)
@description('Name of the environment (used as prefix for all resources)')
param environmentName string

@description('Primary location for all resources')
param location string

@description('Object ID of the user principal to assign roles to')
param principalId string

@description('Tags to apply to all resources')
param tags object = {}

@description('GPT model capacity in 1K TPM units (e.g. 10 = 10K tokens/min, 100 = 100K TPM)')
param gptCapacity int = 300

// ---------------------------------------------------------------------------
// Variables
// ---------------------------------------------------------------------------

var abbrs = {
  resourceGroup: 'rg-'
  aiFoundry: 'aif-'
  aiFoundryProject: 'proj-'
  search: 'srch-'
  storage: 'st'
}

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

// ---------------------------------------------------------------------------
// Resource Group
// ---------------------------------------------------------------------------

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: '${abbrs.resourceGroup}${environmentName}'
  location: location
  tags: tags
}

// ---------------------------------------------------------------------------
// Module Deployments
// ---------------------------------------------------------------------------

module search 'modules/search.bicep' = {
  scope: rg
  params: {
    name: '${abbrs.search}${resourceToken}'
    location: location
    tags: tags
  }
}

module storage 'modules/storage.bicep' = {
  scope: rg
  params: {
    name: '${abbrs.storage}${resourceToken}'
    location: location
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// AI Foundry (embedding model for AI Search vectorizer)
// ---------------------------------------------------------------------------

module aiFoundry 'modules/ai-foundry.bicep' = {
  scope: rg
  params: {
    foundryName: '${abbrs.aiFoundry}${resourceToken}'
    projectName: '${abbrs.aiFoundryProject}${resourceToken}'
    location: location
    tags: tags
    aiSearchId: search.outputs.id
    aiSearchName: search.outputs.name
    storageAccountId: storage.outputs.id
    storageAccountName: storage.outputs.name
    storageContainerName: 'network-data'
    gptCapacity: gptCapacity
  }
}

// ---------------------------------------------------------------------------
// Role Assignments (user + service-to-service, no app identities)
// ---------------------------------------------------------------------------

module roles 'modules/roles.bicep' = {
  scope: rg
  params: {
    principalId: principalId
    foundryName: aiFoundry.outputs.foundryName
    searchName: search.outputs.name
    storageAccountName: storage.outputs.name
    searchPrincipalId: search.outputs.principalId
    foundryPrincipalId: aiFoundry.outputs.foundryPrincipalId
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_AI_FOUNDRY_NAME string = aiFoundry.outputs.foundryName
output AZURE_AI_FOUNDRY_ENDPOINT string = aiFoundry.outputs.foundryEndpoint
output AZURE_AI_FOUNDRY_PROJECT_NAME string = aiFoundry.outputs.projectName
output AZURE_AI_PROJECT_ENDPOINT string = aiFoundry.outputs.projectEndpoint
output AZURE_SEARCH_NAME string = search.outputs.name
output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_STORAGE_ACCOUNT_NAME string = storage.outputs.name
