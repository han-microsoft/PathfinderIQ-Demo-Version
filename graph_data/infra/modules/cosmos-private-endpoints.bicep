// ============================================================================
// Cosmos DB Private Endpoints + Private DNS Zones
//
// Creates a Private Endpoint for the Cosmos DB NoSQL account and links it
// to a Private DNS zone so workloads in the VNet resolve the Cosmos hostname
// to a VNet-internal IP instead of the public endpoint.
//
// Data flow:
//   Container App → VNet outbound → DNS query for cosmos-<token>.documents.azure.com
//   → Private DNS Zone resolves to PE private IP (10.0.2.x)
//   → Traffic stays on Azure backbone, never hits public internet
//
// Resources created:
//   1. Private DNS Zone: privatelink.documents.azure.com
//   2. VNet Link: connects DNS zone to the VNet
//   3. Private Endpoint: connects Cosmos NoSQL to the PE subnet
//   4. DNS Zone Group: auto-registers A record for the Cosmos hostname
//
// Design rationale:
//   Modelled after azure-autonomous-network-demo/infra/modules/cosmos-private-endpoints.bicep.
//   groupIds: ['Sql'] is the Private Link sub-resource for the Cosmos SQL/NoSQL API.
//   registrationEnabled: false — auto-registration is for VMs, not PEs.
//
// Called by: app-main.bicep
// ============================================================================

@description('Azure region for the private endpoint resource')
param location string

@description('Resource tags')
param tags object = {}

@description('Resource ID of the VNet (for DNS zone link)')
param vnetId string

@description('Resource ID of the subnet for private endpoints (snet-private-endpoints)')
param privateEndpointsSubnetId string

@description('Resource ID of the Cosmos DB NoSQL account')
param cosmosNoSqlAccountId string

@description('Name of the Cosmos DB NoSQL account (used for naming PE and DNS link)')
param cosmosNoSqlAccountName string

@description('Optional resource ID of the Cosmos DB Gremlin account for graph and telemetry traffic')
param cosmosGremlinAccountId string = ''

@description('Optional name of the Cosmos DB Gremlin account for graph and telemetry traffic')
param cosmosGremlinAccountName string = ''

// ---------------------------------------------------------------------------
// Private DNS Zone — resolves privatelink.documents.azure.com within the VNet
// DNS zone is global (location: 'global') — not region-specific.
// ---------------------------------------------------------------------------

resource noSqlDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.documents.azure.com'  // Standard zone name for Cosmos NoSQL
  location: 'global'
  tags: tags
}

// ---------------------------------------------------------------------------
// VNet Link — connects the DNS zone to the VNet so workloads can resolve
// Cosmos hostnames via the private DNS zone instead of public DNS.
// registrationEnabled: false — PEs use DNS zone groups, not auto-registration.
// ---------------------------------------------------------------------------

resource noSqlDnsVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: noSqlDnsZone
  name: '${cosmosNoSqlAccountName}-vnet-link'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false  // PE DNS records managed by DNS zone group below
  }
}

// ---------------------------------------------------------------------------
// Private Endpoint — creates a network interface in the PE subnet connected
// to the Cosmos DB NoSQL account via Azure Private Link.
// groupIds: ['Sql'] is the sub-resource for Cosmos SQL/NoSQL API.
// ---------------------------------------------------------------------------

resource noSqlPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${cosmosNoSqlAccountName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointsSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'cosmos-nosql'
        properties: {
          privateLinkServiceId: cosmosNoSqlAccountId  // Target Cosmos account
          groupIds: ['Sql']                           // NoSQL API sub-resource
        }
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// DNS Zone Group — automatically creates an A record in the private DNS zone
// mapping the Cosmos hostname to the PE's private IP address.
// Without this, DNS resolution would still return the public IP.
// ---------------------------------------------------------------------------

resource noSqlDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: noSqlPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'nosql-config'
        properties: {
          privateDnsZoneId: noSqlDnsZone.id  // Link A record to this DNS zone
        }
      }
    ]
  }
}

resource gremlinDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = if (!empty(cosmosGremlinAccountId) && !empty(cosmosGremlinAccountName)) {
  name: 'privatelink.gremlin.cosmos.azure.com'
  location: 'global'
  tags: tags
}

resource gremlinDnsVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (!empty(cosmosGremlinAccountId) && !empty(cosmosGremlinAccountName)) {
  parent: gremlinDnsZone
  name: '${cosmosGremlinAccountName}-vnet-link'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

resource gremlinPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = if (!empty(cosmosGremlinAccountId) && !empty(cosmosGremlinAccountName)) {
  name: 'pe-${cosmosGremlinAccountName}-gremlin'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointsSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'cosmos-gremlin'
        properties: {
          privateLinkServiceId: cosmosGremlinAccountId
          groupIds: ['Gremlin']
        }
      }
    ]
  }
}

resource gremlinDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (!empty(cosmosGremlinAccountId) && !empty(cosmosGremlinAccountName)) {
  parent: gremlinPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'gremlin-config'
        properties: {
          privateDnsZoneId: gremlinDnsZone.id
        }
      }
    ]
  }
}

resource graphSqlPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = if (!empty(cosmosGremlinAccountId) && !empty(cosmosGremlinAccountName)) {
  name: 'pe-${cosmosGremlinAccountName}-sql'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointsSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'cosmos-gremlin-sql'
        properties: {
          privateLinkServiceId: cosmosGremlinAccountId
          groupIds: ['Sql']
        }
      }
    ]
  }
}

resource graphSqlDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (!empty(cosmosGremlinAccountId) && !empty(cosmosGremlinAccountName)) {
  parent: graphSqlPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'graph-nosql-config'
        properties: {
          privateDnsZoneId: noSqlDnsZone.id
        }
      }
    ]
  }
}
