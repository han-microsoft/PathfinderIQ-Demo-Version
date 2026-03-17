// ============================================================================
// Cosmos DB NoSQL — Session persistence + Config snapshots for Container App
//
// Serverless capacity mode — pay-per-request, ~$0 at demo scale.
// RBAC-only auth (no keys) — disableLocalAuthentication: true.
// Public network access disabled — all traffic via Private Endpoint.
// Selective indexing to minimise RU cost on writes.
//
// Resources created:
//   1. Cosmos DB account (serverless NoSQL, RBAC-only, private network)
//   2. Database: "sessions"
//   3. Container: "conversations" (partition key: /session_id, TTL-enabled)
//   4. Container: "config_snapshots" (partition key: /resource_group, TTL 30d)
//
// Outputs:
//   accountName  — for RBAC assignment in deploy.sh
//   accountId    — for PE creation + role scope
//   endpoint     — for COSMOS_SESSION_ENDPOINT env var
//
// Called by: app-main.bicep
// ============================================================================

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

@description('Deterministic resource token for naming')
param resourceToken string

@description('Default TTL in seconds for conversations (7 days = 604800, -1 = disabled)')
param defaultTtl int = 604800

@description('Developer IP address for portal/local access (empty = no public access)')
param devIpAddress string = ''

// ---------------------------------------------------------------------------
// Cosmos DB Account — Serverless NoSQL
// ---------------------------------------------------------------------------

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: 'cosmos-${resourceToken}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      { locationName: location, failoverPriority: 0 }
    ]
    capabilities: [
      { name: 'EnableServerless' }   // Pay-per-request, no provisioned throughput
    ]
    disableLocalAuth: true  // RBAC only — no keys
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'  // Session consistency is sufficient
    }
    // Network: private-only access via Private Endpoint.
    // Optional devIpAddress allows portal/local dev access when needed.
    publicNetworkAccess: 'Disabled'
    ipRules: empty(devIpAddress) ? [] : [
      { ipAddressOrRange: devIpAddress }  // Developer machine IP for local testing
    ]
  }
}

// ---------------------------------------------------------------------------
// Database + Container
// ---------------------------------------------------------------------------

resource sessionsDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name: 'sessions'
  properties: {
    resource: { id: 'sessions' }
  }
}

resource conversationsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: sessionsDb
  name: 'conversations'
  properties: {
    resource: {
      id: 'conversations'
      partitionKey: {
        paths: ['/session_id']
        kind: 'Hash'
      }
      defaultTtl: defaultTtl
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
        includedPaths: [
          { path: '/session_id/?' }
          { path: '/type/?' }
          { path: '/scenario_name/?' }
          { path: '/updated_at/?' }
          { path: '/created_at/?' }
          { path: '/thread/?' }      // Thread discriminator for v2 multi-agent queries
          { path: '/ordinal/?' }     // Handoff ordering within orchestrator conversation
          { path: '/user_id/?' }     // User-scoped session listing (cross-partition)
        ]
        excludedPaths: [
          { path: '/*' }   // Exclude content, tool_calls — saves RU on writes
        ]
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Config Snapshots container — versioned configuration snapshots
// Partition key: /resource_group (one partition per deployment environment).
// TTL: 30 days (2592000 seconds) — old snapshots auto-expire.
// Used by ConfigResolver (Phase 2) to track config drift and provide audit trail.
// ---------------------------------------------------------------------------

resource configSnapshotsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: sessionsDb
  name: 'config_snapshots'
  properties: {
    resource: {
      id: 'config_snapshots'
      partitionKey: {
        paths: ['/resource_group']
        kind: 'Hash'
      }
      defaultTtl: 2592000  // 30 days — config history auto-expires
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
        includedPaths: [
          { path: '/resource_group/?' }  // Partition key — always indexed
          { path: '/version/?' }         // For ORDER BY version DESC queries
          { path: '/timestamp/?' }       // For time-range queries
        ]
        excludedPaths: [
          { path: '/*' }   // Exclude config payload and diff — saves RU on writes
        ]
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output accountName string = cosmosAccount.name
output accountId string = cosmosAccount.id
output endpoint string = cosmosAccount.properties.documentEndpoint
