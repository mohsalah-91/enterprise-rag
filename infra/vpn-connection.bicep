targetScope = 'resourceGroup'

param location string
param connectionName string
param gateway1Id string
param gateway2Id string

@secure()
param sharedKey string

resource connection 'Microsoft.Network/connections@2024-05-01' = {
  name: connectionName
  location: location
  properties: {
    connectionType: 'Vnet2Vnet'
    connectionProtocol: 'IKEv2'
    enableBgp: false
    usePolicyBasedTrafficSelectors: false
    routingWeight: 0
    sharedKey: sharedKey
    virtualNetworkGateway1: {
      id: gateway1Id
    }
    virtualNetworkGateway2: {
      id: gateway2Id
    }
  }
}
