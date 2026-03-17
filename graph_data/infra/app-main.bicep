// ============================================================================
// App Infrastructure — Container App + ACR + CAE + VNet + PE + Identity
//
// Resource-group scoped deployment. Deploys into an EXISTING resource group
// (created by the main data provisioning in main.bicep / azd provision).
//
// All resources use Bicep's native upsert semantics — deploying a resource
// that already exists simply updates it. No conditional logic needed.
//
// RBAC is handled by deploy.sh via `az role assignment create` (naturally
// idempotent) rather than Bicep role assignment resources (which fail with
// RoleAssignmentExists when the GUID doesn't match exactly).
//
// Network architecture:
//   VNet with two subnets:
//     snet-container-apps (/23) — delegated, hosts CAE infrastructure
//     snet-private-endpoints (/24) — hosts PE for Cosmos DB
//   CAE uses external ingress (public URL) but routes outbound through VNet.
//   Cosmos DB has publicNetworkAccess: Disabled — reachable only via PE.
//   Private DNS zone maps Cosmos hostname to PE private IP.
//
// Resources created:
//   1. Virtual Network (2 subnets)
//   2. User-assigned managed identity (for DefaultAzureCredential)
//   3. Log Analytics Workspace (for Container App logs)
//   4. Container Apps Environment (Consumption plan, VNet-integrated)
//   5. Azure Container Registry (Basic, admin enabled)
//   6. Cosmos DB NoSQL (serverless, RBAC-only, private network)
//   7. Private Endpoint + DNS zone for Cosmos DB
//   8. Container App (unified image: nginx + uvicorn)
//
// Usage:
//   az deployment group create \
//     --resource-group <rg-name> \
//     --template-file app-main.bicep \
//     --parameters app-main.bicepparam
//
// Called by: graph_data/deploy.sh --app-infra
// ============================================================================

targetScope = 'resourceGroup'

// ---------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------

@description('Environment name — suffix for deterministic resource naming')
param environmentName string

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Resource tags')
param tags object = {}

@description('Container App display name')
param containerAppName string = 'graph-demo'

@description('AI Foundry account name (passed to deploy.sh for RBAC — not used in Bicep)')
#disable-next-line no-unused-params
param foundryName string

@description('AI Search service name (existing resource in this RG)')
param searchName string

@description('Storage account name (passed to deploy.sh for RBAC — not used in Bicep)')
#disable-next-line no-unused-params
param storageAccountName string

@description('AI Foundry project endpoint for Azure AI Agent Framework')
param projectEndpoint string = ''

@description('LLM model deployment name')
param modelDeploymentName string = 'gpt-4.1'

@description('Active scenario name')
param scenarioName string = ''

@description('Developer IP address for Cosmos DB portal/local access (empty = private-only)')
param devIpAddress string = ''

@description('Package container name for Blob landing zone')
param packageContainerName string = 'scenario-packages'

@description('Package blob root prefix')
param packageBlobRoot string = 'landing/scenarios'

@description('Publish report container name')
param reportContainerName string = 'publish-reports'

@description('Publish report blob root prefix')
param reportBlobRoot string = 'reports/publishes'

@description('Fabric cross-tenant tenant ID')
param fabricTenantId string = ''

@description('Fabric cross-tenant client ID')
param fabricClientId string = ''

// ---------------------------------------------------------------------------
// Variables
// ---------------------------------------------------------------------------

// Deterministic suffix — same formula as main.bicep so names align
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var keyVaultName = 'kv-${resourceToken}'

// ---------------------------------------------------------------------------
// User-Assigned Managed Identity
// DefaultAzureCredential in the container uses this to auth to Azure services.
// Deploying again just updates tags — identity ID and principal ID are stable.
// ---------------------------------------------------------------------------

resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-app-${resourceToken}'
  location: location
  tags: tags
}

// ---------------------------------------------------------------------------
// Virtual Network — provides outbound VNet integration for the CAE and
// a dedicated subnet for Private Endpoints (Cosmos DB).
// ---------------------------------------------------------------------------

module vnet 'modules/vnet.bicep' = {
  name: 'vnet'
  params: {
    name: 'vnet-${resourceToken}'
    location: location
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Log Analytics Workspace — sink for Container App logs
// ---------------------------------------------------------------------------

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'log-cae-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ---------------------------------------------------------------------------
// Container Apps Environment — VNet-integrated hosting (Consumption plan)
//
// internal: false — keeps public ingress (HTTPS endpoint) while routing
// outbound traffic through the VNet. This allows the Container App to reach
// Cosmos DB via Private Endpoint while remaining publicly accessible.
//
// Name uses 'cae-v2-' prefix to force creation of a new environment (the
// original 'cae-' environment has no VNet and cannot be retrofitted).
// ---------------------------------------------------------------------------

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-v2-${resourceToken}'
  location: location
  tags: tags
  properties: {
    vnetConfiguration: {
      infrastructureSubnetId: vnet.outputs.containerAppsSubnetId  // VNet integration
      internal: false  // External ingress — public URL, VNet outbound
    }
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
  }
}

// ---------------------------------------------------------------------------
// Azure Container Registry — stores Docker images
// Basic tier, admin enabled for Container Apps pull via secrets.
// ---------------------------------------------------------------------------

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'cr${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: true
  }
}

// ---------------------------------------------------------------------------
// Cosmos DB NoSQL — Session persistence + Config snapshots (serverless, RBAC-only)
// ---------------------------------------------------------------------------

module cosmosSessionStore 'modules/cosmos-sessions.bicep' = {
  name: 'cosmos-sessions'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    devIpAddress: devIpAddress  // Optional: allow portal/local dev access
  }
}


// ---------------------------------------------------------------------------
// Private Endpoint for Cosmos DB — routes traffic from VNet to Cosmos
// via Azure backbone instead of public internet.
// ---------------------------------------------------------------------------

module cosmosPrivateEndpoints 'modules/cosmos-private-endpoints.bicep' = {
  name: 'cosmos-private-endpoints'
  params: {
    location: location
    tags: tags
    vnetId: vnet.outputs.id
    privateEndpointsSubnetId: vnet.outputs.privateEndpointsSubnetId
    cosmosNoSqlAccountId: cosmosSessionStore.outputs.accountId
    cosmosNoSqlAccountName: cosmosSessionStore.outputs.accountName
  }
}

module keyVault 'modules/key-vault.bicep' = {
  name: 'key-vault'
  params: {
    name: keyVaultName
    location: location
    tags: tags
  }
}




// ---------------------------------------------------------------------------
// Container App — unified image (nginx + uvicorn in one container)
// ---------------------------------------------------------------------------

module app 'modules/container-app.bicep' = {
  params: {
    name: containerAppName
    location: location
    tags: union(tags, { 'azd-service-name': 'app' })
    containerAppsEnvironmentId: cae.id
    containerRegistryName: acr.name
    targetPort: 80
    cpu: '1.0'
    memory: '2Gi'
    identityId: appIdentity.id
    identityClientId: appIdentity.properties.clientId
    projectEndpoint: projectEndpoint
    modelDeploymentName: modelDeploymentName
    aiSearchName: searchName
    scenarioName: scenarioName
    cosmosSessionEndpoint: cosmosSessionStore.outputs.endpoint

        fabricTenantId: fabricTenantId
        fabricClientId: fabricClientId
  }
}

module publishJob 'modules/container-app-job.bicep' = {
  params: {
    name: 'publish-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'publish-job' })
    containerAppsEnvironmentId: cae.id
    containerRegistryName: acr.name
    identityId: appIdentity.id
    identityClientId: appIdentity.properties.clientId
    subscriptionId: subscription().id
    resourceGroupName: resourceGroup().name
    storageAccountName: storageAccountName
    packageContainerName: packageContainerName
    packageBlobRoot: packageBlobRoot
    reportContainerName: reportContainerName
    reportBlobRoot: reportBlobRoot
    aiSearchName: searchName
    aiFoundryName: foundryName
    projectEndpoint: projectEndpoint
    embeddingModel: 'text-embedding-3-small'
    embeddingDimensions: 1536
  }
}

// ---------------------------------------------------------------------------
// Outputs — consumed by deploy.sh for config population and deploy_app.sh
// ---------------------------------------------------------------------------

output VNET_NAME string = vnet.outputs.name
output CONTAINER_APPS_ENV_NAME string = cae.name
output ACR_NAME string = acr.name
output ACR_LOGIN_SERVER string = acr.properties.loginServer
output APP_URL string = app.outputs.uri
output APP_CONTAINER_APP_NAME string = app.outputs.name
output APP_IDENTITY_NAME string = appIdentity.name
output APP_IDENTITY_ID string = appIdentity.id
output APP_IDENTITY_CLIENT_ID string = appIdentity.properties.clientId
output APP_IDENTITY_PRINCIPAL_ID string = appIdentity.properties.principalId
output COSMOS_SESSION_ENDPOINT string = cosmosSessionStore.outputs.endpoint
output COSMOS_SESSION_ACCOUNT string = cosmosSessionStore.outputs.accountName
output KEY_VAULT_NAME string = keyVault.outputs.name
output KEY_VAULT_URI string = keyVault.outputs.vaultUri
output PUBLISH_JOB_NAME string = publishJob.outputs.name

