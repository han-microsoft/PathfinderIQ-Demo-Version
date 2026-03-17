@description('Container Apps Job name')
param name string

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

@description('Container Apps Environment resource ID')
param containerAppsEnvironmentId string

@description('Container Registry name used for image pull')
param containerRegistryName string

@description('Resource ID of the user-assigned managed identity')
param identityId string

@description('Client ID of the user-assigned managed identity')
param identityClientId string

@description('Subscription ID used by publish-time Azure management calls')
param subscriptionId string

@description('Resource group name used by publish-time Azure management calls')
param resourceGroupName string

@description('Storage account name for package and report blobs')
param storageAccountName string

@description('Package container name')
param packageContainerName string

@description('Package blob root prefix')
param packageBlobRoot string

@description('Publish report container name')
param reportContainerName string

@description('Publish report blob root prefix')
param reportBlobRoot string

@description('AI Search service name')
param aiSearchName string

@description('AI Foundry account name')
param aiFoundryName string

@description('AI Foundry project endpoint')
param projectEndpoint string = ''

@description('Embedding model deployment name')
param embeddingModel string = 'text-embedding-3-small'

@description('Embedding dimensions')
param embeddingDimensions int = 1536

@description('Cosmos Gremlin endpoint hostname')
param cosmosGremlinEndpoint string = ''

@description('Cosmos Gremlin account name')
param cosmosGremlinAccountName string = ''

@description('Cosmos Gremlin database name')
param cosmosGremlinDatabase string = 'networkgraph'

@description('Cosmos Gremlin graph name')
param cosmosGremlinGraph string = 'topology'

@description('Cosmos telemetry database name')
param cosmosTelemetryDatabase string = 'telemetry'

@description('Key Vault secret URI for the Cosmos Gremlin primary key')
param cosmosGremlinPrimaryKeySecretUri string = ''

@description('Container image to deploy (initial placeholder; updated by deploy_app.sh)')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

resource publishJob 'Microsoft.App/jobs@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironmentId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 1
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          username: containerRegistry.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: concat([
        {
          name: 'acr-password'
          value: containerRegistry.listCredentials().passwords[0].value
        }
      ], !empty(cosmosGremlinPrimaryKeySecretUri) ? [
        {
          name: 'cosmos-gremlin-primary-key'
          keyVaultUrl: cosmosGremlinPrimaryKeySecretUri
          identity: identityId
        }
      ] : [])
    }
    template: {
      containers: [
        {
          name: 'publisher'
          image: containerImage
          command: [
            'python3'
            '/workspace/graph_data/scripts/publish_job.py'
          ]
          resources: {
            cpu: 1
            memory: '2Gi'
          }
          env: concat([
            { name: 'AZURE_CLIENT_ID', value: identityClientId }
            { name: 'AZURE_SUBSCRIPTION_ID', value: subscriptionId }
            { name: 'AZURE_RESOURCE_GROUP', value: resourceGroupName }
            { name: 'GRAPH_DATA_DIR', value: '/workspace/graph_data' }
            { name: 'STORAGE_ACCOUNT_NAME', value: storageAccountName }
            { name: 'STORAGE_PACKAGE_CONTAINER', value: packageContainerName }
            { name: 'PACKAGE_BLOB_ROOT', value: packageBlobRoot }
            { name: 'STORAGE_REPORTS_CONTAINER', value: reportContainerName }
            { name: 'PUBLISH_REPORT_BLOB_ROOT', value: reportBlobRoot }
            { name: 'AI_SEARCH_NAME', value: aiSearchName }
            { name: 'AI_FOUNDRY_NAME', value: aiFoundryName }
            { name: 'PROJECT_ENDPOINT', value: projectEndpoint }
            { name: 'EMBEDDING_MODEL', value: embeddingModel }
            { name: 'EMBEDDING_DIMENSIONS', value: string(embeddingDimensions) }
            { name: 'COSMOS_GREMLIN_ENDPOINT', value: cosmosGremlinEndpoint }
            { name: 'COSMOS_GREMLIN_ACCOUNT_NAME', value: cosmosGremlinAccountName }
            { name: 'COSMOS_GREMLIN_DATABASE', value: cosmosGremlinDatabase }
            { name: 'COSMOS_GREMLIN_GRAPH', value: cosmosGremlinGraph }
            { name: 'COSMOS_TELEMETRY_DATABASE', value: cosmosTelemetryDatabase }
          ], !empty(cosmosGremlinPrimaryKeySecretUri) ? [
            { name: 'COSMOS_GREMLIN_PRIMARY_KEY', secretRef: 'cosmos-gremlin-primary-key' }
          ] : [])
        }
      ]
    }
  }
}

output id string = publishJob.id
output name string = publishJob.name
