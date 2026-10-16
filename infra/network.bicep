targetScope = 'subscription'

@description('Azure region for all resources.')
param location string = 'centralus'

@secure()
@description('Pre-shared key for the Hub-to-OnPrem VNet-to-VNet VPN connection.')
param vpnSharedKey string

resource hubRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'erag-poc-hub-rg'
  location: location
}

resource onPremRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'erag-poc-onprem-rg'
  location: location
}

resource spokeARg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'erag-poc-spokea-rg'
  location: location
}

resource spokeBRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'erag-poc-spokeb-rg'
  location: location
}

module hubNetwork './network-rg.bicep' = {
  name: 'hub-network'
  scope: hubRg
  params: {
    location: location
    vnetName: 'Hub'
    addressPrefix: '10.0.0.0/16'
    nsgs: [
      {
        name: 'Hub-AzureBastionSubnet-nsg-centralus'
        rules: [
          {
            name: 'AllowSshRdpOutbound'
            properties: {
              priority: 100
              direction: 'Outbound'
              access: 'Allow'
              protocol: '*'
              sourcePortRange: '*'
              destinationPortRanges: [
                '22'
                '3389'
              ]
              sourceAddressPrefix: '*'
              destinationAddressPrefix: 'VirtualNetwork'
            }
          }
          {
            name: 'AllowAzureCloudOutbound'
            properties: {
              priority: 110
              direction: 'Outbound'
              access: 'Allow'
              protocol: 'Tcp'
              sourcePortRange: '*'
              destinationPortRange: '443'
              sourceAddressPrefix: '*'
              destinationAddressPrefix: 'AzureCloud'
            }
          }
          {
            name: 'AllowGatewayManager'
            properties: {
              priority: 2702
              direction: 'Inbound'
              access: 'Allow'
              protocol: '*'
              sourcePortRange: '*'
              destinationPortRange: '443'
              sourceAddressPrefix: 'GatewayManager'
              destinationAddressPrefix: '*'
            }
          }
          {
            name: 'AllowHttpsInBound'
            properties: {
              priority: 2703
              direction: 'Inbound'
              access: 'Allow'
              protocol: '*'
              sourcePortRange: '*'
              destinationPortRange: '443'
              sourceAddressPrefix: 'Internet'
              destinationAddressPrefix: '*'
            }
          }
        ]
      }
    ]
    subnets: [
      {
        name: 'GatewaySubnet'
        prefix: '10.0.0.0/27'
        nsgName: ''
      }
      {
        name: 'AzureBastionSubnet'
        prefix: '10.0.1.0/26'
        nsgName: 'Hub-AzureBastionSubnet-nsg-centralus'
      }
    ]
  }
}

module onPremNetwork './network-rg.bicep' = {
  name: 'onprem-network'
  scope: onPremRg
  params: {
    location: location
    vnetName: 'On-prem'
    addressPrefix: '10.100.0.0/16'
    nsgs: [
      {
        name: 'On-prem-sql-nsg-centralus'
        rules: []
      }
    ]
    subnets: [
      {
        name: 'GatewaySubnet'
        prefix: '10.100.0.0/27'
        nsgName: ''
      }
      {
        name: 'sql'
        prefix: '10.100.1.0/24'
        nsgName: 'On-prem-sql-nsg-centralus'
      }
    ]
  }
}

module spokeANetwork './network-rg.bicep' = {
  name: 'spokea-network'
  scope: spokeARg
  params: {
    location: location
    vnetName: 'SpokeA'
    addressPrefix: '10.1.0.0/16'
    nsgs: [
      {
        name: 'SpokeA-aks-nodes-nsg-centralus'
        rules: []
      }
      {
        name: 'SpokeA-mgmt-nsg-centralus'
        rules: []
      }
      {
        name: 'SpokeA-private-endpoints-nsg-centralus'
        rules: []
      }
      {
        name: 'SpokeA-postgres-nsg-centralus'
        rules: []
      }
    ]
    subnets: [
      {
        name: 'aks-nodes'
        prefix: '10.1.0.0/22'
        nsgName: ''
      }
      {
        name: 'private-endpoints'
        prefix: '10.1.8.0/24'
        nsgName: ''
      }
      {
        name: 'postgres'
        prefix: '10.1.9.0/24'
        nsgName: 'SpokeA-postgres-nsg-centralus'
      }
      {
        name: 'mgmt'
        prefix: '10.1.10.0/24'
        nsgName: ''
      }
    ]
  }
}

module spokeBNetwork './network-rg.bicep' = {
  name: 'spokeb-network'
  scope: spokeBRg
  params: {
    location: location
    vnetName: 'SpokeB'
    addressPrefix: '10.2.0.0/16'
    nsgs: []
    subnets: [
      {
        name: 'agent'
        prefix: '10.2.0.0/24'
        nsgName: ''
      }
      {
        name: 'private-endpoints'
        prefix: '10.2.1.0/24'
        nsgName: ''
      }
      {
        name: 'tools'
        prefix: '10.2.2.0/24'
        nsgName: ''
      }
    ]
  }
}

module hubGateway './vpn-gateway.bicep' = {
  name: 'hub-gateway'
  scope: hubRg
  params: {
    location: location
    vnetName: 'Hub'
    gatewayName: 'GW-Hub'
    publicIpName1: 'GW-Hub-IP1'
    publicIpName2: 'GW-Hub-IP2'
  }
  dependsOn: [
    hubNetwork
  ]
}

module onPremGateway './vpn-gateway.bicep' = {
  name: 'onprem-gateway'
  scope: onPremRg
  params: {
    location: location
    vnetName: 'On-prem'
    gatewayName: 'GW-OnPrem'
    publicIpName1: 'GW-OnPrem-IP1'
    publicIpName2: 'GW-OnPrem-IP2'
  }
  dependsOn: [
    onPremNetwork
  ]
}

module hubBastion './bastion.bicep' = {
  name: 'hub-bastion'
  scope: hubRg
  params: {
    location: location
    vnetName: 'Hub'
    bastionName: 'Hub-Bastion'
    publicIpName: 'hub-bastion'
  }
  dependsOn: [
    hubNetwork
  ]
}

module hubToSpokeAPeering './vnet-peering.bicep' = {
  name: 'hub-to-spokea-peering'
  scope: hubRg
  params: {
    localVnetName: 'Hub'
    peeringName: 'Hub-to-SpokeA'
    remoteVnetId: spokeANetwork.outputs.vnetId
    allowGatewayTransit: true
    useRemoteGateways: false
  }
  dependsOn: [
    hubGateway
  ]
}

module spokeAToHubPeering './vnet-peering.bicep' = {
  name: 'spokea-to-hub-peering'
  scope: spokeARg
  params: {
    localVnetName: 'SpokeA'
    peeringName: 'SpokeA-to-Hub'
    remoteVnetId: hubNetwork.outputs.vnetId
    allowGatewayTransit: false
    useRemoteGateways: true
  }
  dependsOn: [
    hubGateway
  ]
}

module hubToSpokeBPeering './vnet-peering.bicep' = {
  name: 'hub-to-spokeb-peering'
  scope: hubRg
  params: {
    localVnetName: 'Hub'
    peeringName: 'Hub-to-SpokeB'
    remoteVnetId: spokeBNetwork.outputs.vnetId
    allowGatewayTransit: true
    useRemoteGateways: false
  }
  dependsOn: [
    hubGateway
  ]
}

module spokeBToHubPeering './vnet-peering.bicep' = {
  name: 'spokeb-to-hub-peering'
  scope: spokeBRg
  params: {
    localVnetName: 'SpokeB'
    peeringName: 'SpokeB-to-Hub'
    remoteVnetId: hubNetwork.outputs.vnetId
    allowGatewayTransit: false
    useRemoteGateways: true
  }
  dependsOn: [
    hubGateway
  ]
}

module hubToOnPremConnection './vpn-connection.bicep' = {
  name: 'hub-to-onprem-connection'
  scope: hubRg
  params: {
    location: location
    connectionName: 'Conn-Hub-to-OnPrem'
    gateway1Id: hubGateway.outputs.gatewayId
    gateway2Id: onPremGateway.outputs.gatewayId
    sharedKey: vpnSharedKey
  }
}

output hubVnetId string = hubNetwork.outputs.vnetId
output onPremVnetId string = onPremNetwork.outputs.vnetId
output spokeAVnetId string = spokeANetwork.outputs.vnetId
output spokeBVnetId string = spokeBNetwork.outputs.vnetId
