// ============================================================================
// Role Assignments — User roles + service-to-service roles
// No Cosmos DB, no Container App / Web App identities.
// ============================================================================

@description('Object ID of the user principal')
param principalId string

@description('Name of the AI Foundry resource (CognitiveServices account)')
param foundryName string

@description('Name of the AI Search resource')
param searchName string

@description('Name of the Storage account')
param storageAccountName string

@description('Principal ID of the AI Search service (system-assigned identity)')
param searchPrincipalId string

@description('Principal ID of the AI Foundry resource (system-assigned identity)')
param foundryPrincipalId string

// ---------------------------------------------------------------------------
// Built-in Role Definition GUIDs
// ---------------------------------------------------------------------------

var roles = {
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  storageBlobDataReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  cognitiveServicesOpenAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  cognitiveServicesContributor: '25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
}

// ---------------------------------------------------------------------------
// Reference existing resources
// ---------------------------------------------------------------------------

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryName
}

resource search 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchName
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

// ============================================================================
// USER ROLE ASSIGNMENTS
// ============================================================================

// User → Storage Blob Data Contributor (upload/manage runbook files)
resource userStorageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, principalId, roles.storageBlobDataContributor)
  scope: storageAccount
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
    principalType: 'User'
  }
}

// User → Cognitive Services OpenAI User (invoke models via Foundry resource)
resource userOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, principalId, roles.cognitiveServicesOpenAiUser)
  scope: foundry
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAiUser)
    principalType: 'User'
  }
}

// User → Cognitive Services Contributor (manage Foundry resource, projects, and connections)
resource userCognitiveServicesContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, principalId, roles.cognitiveServicesContributor)
  scope: foundry
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesContributor)
    principalType: 'User'
  }
}

// User → Search Index Data Contributor (manage index data)
resource userSearchIndexContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, principalId, roles.searchIndexDataContributor)
  scope: search
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchIndexDataContributor)
    principalType: 'User'
  }
}

// User → Search Service Contributor (manage search service configuration)
resource userSearchServiceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, principalId, roles.searchServiceContributor)
  scope: search
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchServiceContributor)
    principalType: 'User'
  }
}

// ============================================================================
// SERVICE-TO-SERVICE ROLE ASSIGNMENTS
// ============================================================================

// AI Search → Storage Blob Data Reader (indexer reads blob data)
resource searchStorageBlobReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, searchPrincipalId, roles.storageBlobDataReader)
  scope: storageAccount
  properties: {
    principalId: searchPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataReader)
    principalType: 'ServicePrincipal'
  }
}

// AI Search → OpenAI User (search uses embeddings for vectorization via Foundry)
resource searchOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, searchPrincipalId, roles.cognitiveServicesOpenAiUser)
  scope: foundry
  properties: {
    principalId: searchPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAiUser)
    principalType: 'ServicePrincipal'
  }
}

// Foundry → Storage Blob Data Contributor (Agent Service reads/writes files)
resource foundryStorageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, foundryPrincipalId, roles.storageBlobDataContributor)
  scope: storageAccount
  properties: {
    principalId: foundryPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
    principalType: 'ServicePrincipal'
  }
}

// Foundry → Search Index Data Contributor (Agent Service manages search indexes)
resource foundrySearchIndexContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, foundryPrincipalId, roles.searchIndexDataContributor)
  scope: search
  properties: {
    principalId: foundryPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchIndexDataContributor)
    principalType: 'ServicePrincipal'
  }
}

// Foundry → Search Service Contributor (Agent Service manages search service config)
resource foundrySearchServiceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, foundryPrincipalId, roles.searchServiceContributor)
  scope: search
  properties: {
    principalId: foundryPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchServiceContributor)
    principalType: 'ServicePrincipal'
  }
}
