// ============================================================================
// Parameters file for App Infrastructure (Container App + ACR + Identity)
//
// Reads from environment variables populated by deploy.sh / azure_config.env.
// This is a resource-group scoped deployment — the RG must already exist.
//
// Usage:
//   source azure_config.env
//   az deployment group create \
//     --resource-group "$AZURE_RESOURCE_GROUP" \
//     --template-file infra/app-main.bicep \
//     --parameters infra/app-main.bicepparam
// ============================================================================

using './app-main.bicep'

param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'graph-data')
param location = readEnvironmentVariable('AZURE_LOCATION', 'swedencentral')
param containerAppName = readEnvironmentVariable('CONTAINER_APP_NAME', 'graph-demo')
param foundryName = readEnvironmentVariable('AI_FOUNDRY_NAME', '')
param searchName = readEnvironmentVariable('AI_SEARCH_NAME', '')
param storageAccountName = readEnvironmentVariable('STORAGE_ACCOUNT_NAME', '')
param projectEndpoint = readEnvironmentVariable('PROJECT_ENDPOINT', '')
param modelDeploymentName = readEnvironmentVariable('CHAT_MODEL_DEPLOYMENT', 'gpt-4.1')
param scenarioName = readEnvironmentVariable('DEFAULT_SCENARIO', '')
param devIpAddress = readEnvironmentVariable('DEV_IP_ADDRESS', '')
param packageContainerName = readEnvironmentVariable('STORAGE_PACKAGE_CONTAINER', 'scenario-packages')
param packageBlobRoot = readEnvironmentVariable('PACKAGE_BLOB_ROOT', 'landing/scenarios')
param reportContainerName = readEnvironmentVariable('STORAGE_REPORTS_CONTAINER', 'publish-reports')
param reportBlobRoot = readEnvironmentVariable('PUBLISH_REPORT_BLOB_ROOT', 'reports/publishes')
param fabricTenantId = readEnvironmentVariable('FABRIC_TENANT_ID', '')
param fabricClientId = readEnvironmentVariable('FABRIC_CLIENT_ID', '')

param tags = {
  project: 'graph-demo'
  environment: readEnvironmentVariable('AZURE_ENV_NAME', 'graph-data')
}
