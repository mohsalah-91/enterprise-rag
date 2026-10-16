targetScope = 'resourceGroup'

param location string
param vnetName string
param addressPrefix string
param nsgs array
param subnets array

resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = [for definition in nsgs: {
  name: definition.name
  location: location
  properties: {
    securityRules: definition.rules
  }
}]

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: vnetName
  location: location
  dependsOn: [
    nsg
  ]
  properties: {
    addressSpace: {
      addressPrefixes: [
        addressPrefix
      ]
    }
    subnets: [for subnet in subnets: {
      name: subnet.name
      properties: {
        addressPrefix: subnet.prefix
        defaultOutboundAccess: false
        privateEndpointNetworkPolicies: 'Disabled'
        networkSecurityGroup: empty(subnet.nsgName) ? null : {
          id: resourceId('Microsoft.Network/networkSecurityGroups', subnet.nsgName)
        }
      }
    }]
  }
}

output vnetId string = vnet.id
