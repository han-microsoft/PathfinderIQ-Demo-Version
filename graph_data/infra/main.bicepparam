// ============================================================================
// Parameters file for Graph Data Provisioner
//
// Deploys AI Foundry (embeddings), AI Search, and Storage.
// No apps, no Cosmos DB, no VNet.
//
// Set environment variables before deploying:
//   AZURE_ENV_NAME        — e.g. "graph-data"
//   AZURE_LOCATION        — e.g. "swedencentral"
//   AZURE_PRINCIPAL_ID    — your user object ID (az ad signed-in-user show --query id -o tsv)
// ============================================================================

using './main.bicep'

param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'graph-data')
param location = readEnvironmentVariable('AZURE_LOCATION', 'swedencentral')
param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID', '')
param gptCapacity = int(readEnvironmentVariable('GPT_CAPACITY_1K_TPM', '300'))
param tags = {
  project: 'graph-data-provisioner'
  environment: readEnvironmentVariable('AZURE_ENV_NAME', 'graph-data')
}

// Deploy:
//   azd up    # Provisions infra, then run deploy.sh --provision-all for data
