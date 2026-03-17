// ============================================================================
// Container App — Unified single-container deployment
//
// Deploys one Container App with:
//   - User-assigned managed identity (for Azure service auth via DefaultAzureCredential)
//   - ACR image pull via admin credentials
//   - External HTTPS ingress on configurable target port
//   - Environment variables for all backend configuration
//   - HTTP-based autoscaling (1–3 replicas)
//
// The initial deployment uses a placeholder image from MCR. The real image
// is pushed by deploy_app.sh after infrastructure provisioning.
//
// Dependents:
//   Referenced by app-main.bicep.
// ============================================================================

@description('Name of the Container App')
param name string

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

@description('Container Apps Environment resource ID (from container-apps-environment module)')
param containerAppsEnvironmentId string

@description('Container Registry name (ACR — used to retrieve login server and admin credentials)')
param containerRegistryName string

@description('Container image to deploy (initial placeholder; updated by deploy_app.sh)')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Target port exposed by the container (nginx listens on 80 in the unified image)')
param targetPort int = 80

@description('CPU cores allocated to the container')
param cpu string = '1.0'

@description('Memory allocated to the container')
param memory string = '2Gi'

@description('Minimum replica count (1 = always-on)')
param minReplicas int = 1

@description('Maximum replica count for autoscaling')
param maxReplicas int = 3

// -- App configuration (injected as environment variables) --------------------

@description('AI Foundry project endpoint (used by Azure AI Agent Framework)')
param projectEndpoint string = ''

@description('LLM model deployment name (e.g. gpt-4.1, gpt-5.2)')
param modelDeploymentName string = 'gpt-5.2'

@description('AI Search service name (used to construct endpoint URL)')
param aiSearchName string = ''

@description('Active scenario name (subfolder under graph_data/data/scenarios/)')
param scenarioName string = ''

@description('Resource ID of the user-assigned managed identity')
param identityId string

@description('Client ID of the user-assigned managed identity (for DefaultAzureCredential)')
param identityClientId string

@description('Cosmos DB NoSQL endpoint for session persistence (empty = in-memory)')
param cosmosSessionEndpoint string = ''

@description('Fabric cross-tenant tenant ID')
param fabricTenantId string = ''

@description('Fabric cross-tenant client ID')
param fabricClientId string = ''

// ---------------------------------------------------------------------------
// Reference existing ACR — needed for login server URL and admin credentials
// ---------------------------------------------------------------------------

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

// ---------------------------------------------------------------------------
// Container App — single container serving nginx (frontend) + uvicorn (backend)
// ---------------------------------------------------------------------------

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}          // Attach user-assigned MI for Azure service auth
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironmentId
    configuration: {
      ingress: {
        external: true             // Public HTTPS endpoint
        targetPort: targetPort     // nginx listens on port 80 inside the container
        transport: 'auto'
        allowInsecure: false       // Force HTTPS
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          username: containerRegistry.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: containerRegistry.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'app'
          image: containerImage
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: concat([
            // -- LLM provider config --
            { name: 'LLM_PROVIDER', value: 'agent' }
            { name: 'LLM_MODEL', value: modelDeploymentName }
            { name: 'AZURE_AI_PROJECT_ENDPOINT', value: projectEndpoint }
            { name: 'AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME', value: modelDeploymentName }
            // -- Managed identity: tells DefaultAzureCredential which identity to use --
            { name: 'AZURE_CLIENT_ID', value: identityClientId }
            // -- Azure AI Search --
            { name: 'AI_SEARCH_ENDPOINT', value: !empty(aiSearchName) ? 'https://${aiSearchName}.search.windows.net' : '' }
            // -- Scenario --
            { name: 'SCENARIO_NAME', value: scenarioName }
            // -- Session persistence (Cosmos DB NoSQL — empty = in-memory fallback) --
            { name: 'COSMOS_SESSION_ENDPOINT', value: cosmosSessionEndpoint }
            // -- Server --
            { name: 'CORS_ORIGINS', value: '["*"]' }
            { name: 'DEBUG', value: 'false' }
          ], !empty(fabricTenantId) ? [
            // -- Fabric cross-tenant credentials --
            { name: 'FABRIC_TENANT_ID', value: fabricTenantId }
            { name: 'FABRIC_CLIENT_ID', value: fabricClientId }
          ] : [])
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scale-rule'
            http: {
              metadata: { concurrentRequests: '100' }  // Scale up at 100 concurrent requests
            }
          }
        ]
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs — consumed by app-main.bicep for RBAC and config population
// ---------------------------------------------------------------------------

output id string = containerApp.id
output name string = containerApp.name
output fqdn string = containerApp.properties.configuration.ingress.fqdn
output uri string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
