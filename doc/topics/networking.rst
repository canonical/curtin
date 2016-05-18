==========
Networking
==========

Curtin supports a user-configurable networking configuration format.
This format lets users (including via MAAS) to customize their machines'
networking interfaces by assigning subnet configuration, virtual device
creation (bonds, bridges, vlans) routes and DNS configuration.

Format
------
Curtin accepts a YAML input under the top-level ``network`` key
to indicate that a user would like to specify a custom networking
configuration.  Required elements of a network configuration are
``config`` and ``version``.  Currently curtin only supports 
network config version=1. ::

  network:
    version: 1
    config:
       
Config Types
------------
Within the network ``config`` portion, users include a list of configuration
types.  The current list of support ``type`` values are as follows:
  
 - **physical**: "Physical" network devices, like ethernet which are identified by MAC address.
 - **bridge**: A software Linux Bridge device
 - **bond**:  A software Linux Bond device
 - **vlan**:  A software Linux VLAN device

**Physical Example**::
  
  network:
    version: 1
    config:
      # Simple network adapter
      - type: physical
        name: interface0
        mac_address: 00:11:22:33:44:55
      # Second nic with Jumbo frames
      - type: physical
        name: jumbo0
        mac_address: aa:11:22:33:44:55
        mtu: 9000
      # 10G pair
      - type: physical
        name: gbe0
        mac_address: cd:11:22:33:44:00
      - type: physical
        name: gbe1
        mac_address: cd:11:22:33:44:02

**Bridge Example**::

   network:
    version: 1
    config:
      # Simple network adapter
      - type: physical
        name: interface0
        mac_address: 00:11:22:33:44:55
      # Second nic with Jumbo frames
      - type: physical
        name: jumbo0
        mac_address: aa:11:22:33:44:55
        mtu: 9000
      - type: bridge
        name: br0
        bridge_interfaces:
          - jumbo0
        params:
          bridge_stp: "off"
          bridge_fd: 0
          bridge_maxwait: 0
      
**Bond Example**::

   network:
    version: 1
    config:
      # Simple network adapter
      - type: physical
        name: interface0
        mac_address: 00:11:22:33:44:55
      # 10G pair
      - type: physical
        name: gbe0
        mac_address: cd:11:22:33:44:00
      - type: physical
        name: gbe1
        mac_address: cd:11:22:33:44:02
      - type: bond
        name: bond0
        bond_interfaces:
          - gbe0
          - gbe1
        params:
          bond-mode: active-backup
   
**VLAN Example**::

   network:
     version: 1
     config:
       # Physical interfaces.
       - type: physical
         name: eth0
         mac_address: "c0:d6:9f:2c:e8:80"
       # VLAN interface.
       - type: vlan
         name: eth0.101
         vlan_link: eth0
         vlan_id: 101
         mtu: 1500


Subnet/IP configuration
-----------------------

For any network device (one of the Config Types) users can define a list of
``subnets`` which contain ip configuration dictionaries.  Multiple subnet
entries will create interface alias allowing a single interface to use different
ip configurations.  

Valid keys for for `subnets` include the following:

 - **type**: Specify the subnet type.
 - **control**: Specify manual, auto or hotplug.  Indicates how the interface will be handled during boot.
 - **address**: IPv4 or IPv6 address.  It may include CIDR netmask notation.
 - **netmask**: IPv4 subnet mask in dotted format or CIDR notation.
 - **gateway**: IPv4 address of the default gateway for this subnet.
 - **dns_nameserver**: Specify a list of IPv4 dns server IPs to end up in resolv.conf.
 - **dns_search**: Specify a list of search paths to be included in resolv.conf.


Subnet types are one of the following:

 - **dhcp4**: Configure this interface with IPv4 dhcp.
 - **dhcp**: Alias for ``dhcp4``
 - **dhcp6**: Configure this interface with IPv6 dhcp.
 - **static**: Configure this interface with a static IPv4.
 - **static6**: Configure this interface with a static IPv6 .

When making use of ``dhcp`` types, no additional configuration is needed in the
subnet dictionary.


**Subnet DHCP Example**::

   network:
     version: 1
     config:
       - type: physical
         name: interface0
         mac_address: 00:11:22:33:44:55
         subnets:
           - type: dhcp


**Subnet Static Example**::

   network:
     version: 1
     config:
       - type: physical
         name: interface0
         mac_address: 00:11:22:33:44:55
         subnets:
           - type: static
             address: 192.168.23.14/27
             gateway: 192.168.23.1
             dns_nameservers:
               - 192.168.23.2
               - 8.8.8.8
             dns_search:
               - exemplary.maas

The following will result in an `interface0` using DHCP and `interface0:1`
using the static subnet configuration.

**Multiple subnet Example**::

   network:
     version: 1
     config:
       - type: physical
         name: interface0
         mac_address: 00:11:22:33:44:55
         subnets:
         subnets:
           - type: dhcp
           - type: static
             address: 192.168.23.14/27
             gateway: 192.168.23.1
             dns_nameservers:
               - 192.168.23.2
               - 8.8.8.8
             dns_search:
               - exemplary.maas




Nameservers
-----------

Users can specify a ``nameserver`` type.  Nameserver dictionaries include
the following keys:

 - **address**: List of IPv4 or IPv6 address of nameservers.
 - **search**: List of of hostnames to include in the resolv.conf search path.


Routes
------

Users can include static routing information as well.  A ``route`` dictionary
has the following keys:

 - **destination**: IPv4 network address with CIDR netmask notation.
 - **gateway**: IPv4 gateway address with CIDR netmask notation.
 - **metric**: Integer which sets the network metric value for this route.
 - **device**: Specify the network device that will deliver packets for this route.


Multi-layered configurations
----------------------------

A vlan'ed bonded bridged set of interfaces.


More Examples
-------------

Multiple VLAN example ::

  network:
    version: 1
    config:
    - id: eth0
      mac_address: d4:be:d9:a8:49:13
      mtu: 1500
      name: eth0
      subnets:
      - address: 10.245.168.16/21
        dns_nameservers:
        - 10.245.168.2
        gateway: 10.245.168.1
        type: static
      type: physical
    - id: eth1
      mac_address: d4:be:d9:a8:49:15
      mtu: 1500
      name: eth1
      subnets:
      - address: 10.245.188.2/24
        dns_nameservers: []
        type: static
      type: physical
    - id: eth2
      mac_address: d4:be:d9:a8:49:17
      mtu: 1500
      name: eth2
      subnets:
      - type: manual
      type: physical
    - id: eth3
      mac_address: d4:be:d9:a8:49:19
      mtu: 1500
      name: eth3
      subnets:
      - type: manual
      type: physical
    - id: eth1.2667
      mtu: 1500
      name: eth1.2667
      subnets:
      - address: 10.245.184.2/24
        dns_nameservers: []
        type: static
      type: vlan
      vlan_id: 2667
      vlan_link: eth1
    - id: eth1.2668
      mtu: 1500
      name: eth1.2668
      subnets:
      - address: 10.245.185.1/24
        dns_nameservers: []
        type: static
      type: vlan
      vlan_id: 2668
      vlan_link: eth1
    - id: eth1.2669
      mtu: 1500
      name: eth1.2669
      subnets:
      - address: 10.245.186.1/24
        dns_nameservers: []
        type: static
      type: vlan
      vlan_id: 2669
      vlan_link: eth1
    - id: eth1.2670
      mtu: 1500
      name: eth1.2670
      subnets:
      - address: 10.245.187.2/24
        dns_nameservers: []
        type: static
      type: vlan
      vlan_id: 2670
      vlan_link: eth1
    - address: 10.245.168.2
      search:
      - dellstack
      type: nameserver

