// ============================================================================
// Virtual Network — Container Apps subnet + Private Endpoints subnet
//
// Provides network isolation for Container Apps outbound traffic and private
// connectivity to backend services (Cosmos DB) via Private Endpoints.
//
// Subnet layout:
//   snet-container-apps    /23 (512 IPs) — delegated to Microsoft.App/environments
//   snet-private-endpoints /24 (256 IPs) — hosts Private Endpoints (no delegation)
//
// The /23 is the minimum required by Container Apps. The /24 is generous for
// PEs — each PE consumes one IP, so 256 is plenty for future services.
//
// Design rationale:
//   Modelled after azure-autonomous-network-demo/infra/modules/vnet.bicep.
//   No NSGs — Container Apps manages its own network rules. NSGs can be
//   added later if the threat model requires them.
//
// Resources created:
//   1. Virtual Network with two subnets
//
// Outputs:
//   id                       — VNet resource ID
//   name                     — VNet name
//   containerAppsSubnetId    — subnet ID for CAE infrastructure
//   privateEndpointsSubnetId — subnet ID for Private Endpoints
//
// Called by: app-main.bicep
// ============================================================================

@description('Name of the virtual network')
param name string

@description('Azure region')
param location string

@description('Resource tags')
param tags object = {}

@description('Address space for the VNet (must contain both subnet prefixes)')
param addressPrefix string = '10.0.0.0/16'

@description('Address prefix for the Container Apps subnet (/23 minimum required by CAE)')
param containerAppsSubnetPrefix string = '10.0.0.0/23'

@description('Address prefix for the Private Endpoints subnet')
param privateEndpointsSubnetPrefix string = '10.0.2.0/24'

// ---------------------------------------------------------------------------
// Virtual Network — single VNet with two subnets
// ---------------------------------------------------------------------------

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [addressPrefix]  // 10.0.0.0/16 = 65,536 IPs total
    }
    subnets: [
      {
        // Container Apps subnet — delegated so Azure manages NSG-like rules.
        // /23 = 512 IPs, minimum required by Container Apps Environment.
        name: 'snet-container-apps'
        properties: {
          addressPrefix: containerAppsSubnetPrefix
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'  // Required delegation for CAE
              }
            }
          ]
        }
      }
      {
        // Private Endpoints subnet — no delegation required.
        // Each PE consumes one private IP from this range.
        name: 'snet-private-endpoints'
        properties: {
          addressPrefix: privateEndpointsSubnetPrefix
        }
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// Outputs — consumed by app-main.bicep for CAE + PE wiring
// ---------------------------------------------------------------------------

output id string = vnet.id
output name string = vnet.name
output containerAppsSubnetId string = vnet.properties.subnets[0].id
output privateEndpointsSubnetId string = vnet.properties.subnets[1].id
