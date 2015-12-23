#!/usr/bin/python

# This script creates TNO North/TNO south mininet topology
# author:PZ, inspired by ONOS sdnip tutorial

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import setLogLevel, info, debug
from mininet.node import Host, RemoteController
from mininet.node import Switch
from mininet.nodelib import LinuxBridge

#QUAGGA_DIR = '/usr/lib/quagga'
QUAGGA_DIR = '/usr/sbin'
# Must exist and be owned by quagga user (quagga:quagga by default on Ubuntu)
QUAGGA_RUN_DIR = '/var/run/quagga'
CONFIG_DIR = '/home/coco/coco_scripts/bgp_configs'

class SdnIpHost(Host):
    def __init__(self, name, ip, route, *args, **kwargs):
        Host.__init__(self, name, ip=ip, *args, **kwargs)

        self.route = route

    def config(self, **kwargs):
        Host.config(self, **kwargs)

        debug("configuring route %s" % self.route)

        self.cmd('ip route add default via %s' % self.route)

class PingableHost(Host):
    def __init__(self, name, ip, mac, remoteIP, remoteMAC, *args, **kwargs):
        Host.__init__(self, name, ip=ip, mac=mac, *args, **kwargs)

        self.remoteIP = remoteIP
        self.remoteMAC = remoteMAC

    def config(self, **kwargs):
        Host.config(self, **kwargs)

        debug("configuring arp for %s %s" % (self.remoteIP, self.remoteMAC))

        self.setARP(self.remoteIP, self.remoteMAC)

class Router(Host):
    def __init__(self, name, quaggaConfFile, zebraConfFile, intfDict, ARPDict, *args, **kwargs):
        Host.__init__(self, name, *args, **kwargs)

        self.quaggaConfFile = quaggaConfFile
        self.zebraConfFile = zebraConfFile
        self.intfDict = intfDict
        # TODO should be optional?
        self.ARPDict = ARPDict

    def config(self, **kwargs):
        Host.config(self, **kwargs)
        self.cmd('sysctl net.ipv4.ip_forward=1')

        for intf, attrs in self.intfDict.items():
            self.cmd('ip addr flush dev %s' % intf)
            if 'mac' in attrs:
                self.cmd('ip link set %s down' % intf)
                self.cmd('ip link set %s address %s' % (intf, attrs['mac']))
                self.cmd('ip link set %s up ' % intf)
            #for addr in attrs['ipAddrs']:
            if 'vlan' in attrs:
                #self.cmd('ip addr flush dev %s')
                self.cmd('ip link add link %s name %s.%s type vlan id %s' % (intf, intf, attrs['vlan'], attrs['vlan']))
                self.cmd('ip addr add %s dev %s.%s' % (attrs['ipAddrs'], intf, attrs['vlan']))
                self.cmd('ip link set dev %s.%s up' % (intf, attrs['vlan']))
            if ('ipAddrs' in attrs) & ('vlan' not in attrs):
                self.cmd('ip addr add %s dev %s' % (attrs['ipAddrs'], intf))

        self.cmd('%s/zebra -d -f %s -z %s/zebra%s.api -i %s/zebra%s.pid' % (QUAGGA_DIR,self.zebraConfFile, QUAGGA_RUN_DIR, self.name, QUAGGA_RUN_DIR, self.name))
        self.cmd('%s/bgpd -d -f %s -z %s/zebra%s.api -i %s/bgpd%s.pid' % (QUAGGA_DIR,self.quaggaConfFile, QUAGGA_RUN_DIR, self.name, QUAGGA_RUN_DIR, self.name))

        for attrs in self.ARPDict.itervalues():
            if 'localdev' in attrs:
                self.cmd('ip route add %s%s dev %s' % (attrs['remoteIP'], attrs['remoteMask'], attrs['localdev']))
                self.setARP(attrs['remoteIP'], attrs['remoteMAC'])
            elif 'nexthop' in attrs:
                self.cmd('ip route add %s%s via %s' % (attrs['remoteIP'], attrs['remoteMask'], attrs['nexthop']))
                self.setARP(attrs['nexthop'], attrs['remoteMAC'])





    def terminate(self):
        self.cmd("ps ax | egrep 'bgpd%s.pid|zebra%s.pid' | awk '{print $1}' | xargs kill" % (self.name, self.name))

        Host.terminate(self)


class MDCoCoTopoNorth(Topo):
    # TODO : call MDCoCoTopo with domain name parameter
    # we were not successful with
    #def __init__(self, domainname):
    #    Topo.__init__(self, domainname)
    #    self.domainname = domainname

    "Multidomain CoCo topology - TNO North"

    def build( self ):
        domID = 2

        tn_pe1 = self.addSwitch('tn-pe1', dpid='0000000000000021', datapath='user')
        tn_pc1 = self.addSwitch('tn-pc1', dpid='0000000000000022', datapath='user')
        tn_pe2 = self.addSwitch('tn-pe2', dpid='0000000000000023', datapath='user')
        tn_gw_ts = self.addSwitch('tn-gw-ts', dpid='0000000000000024')

        #tn_pe1 = self.addSwitch('tn-pe1', dpid='0000000000000021')
        #tn_pc1 = self.addSwitch('tn-pc1', dpid='0000000000000022')
        #tn_pe2 = self.addSwitch('tn-pe2', dpid='0000000000000023')

# [PZ] perhaps we will add s4 later; now we want to avoid loop problems
#        s4 = self.addSwitch('s4', dpid='0000000000000004')

        # add pingable hosts at the edges
        # TODO : for any kind of multihoming pingable hosts should have a dictionary of arp entries, not just one?
        pinghost = self.addHost('tn-ph-sn', cls=PingableHost, ip='10.0.0.2/24', mac='00:10:00:00:00:02', remoteIP='10.0.0.1', remoteMAC='00:10:00:00:00:01')
        self.addLink(tn_pe1, pinghost)

        pinghost = self.addHost('tn-ph-ts', cls=PingableHost, ip='10.0.0.3/24', mac='00:10:00:00:00:03', remoteIP='10.0.0.4', remoteMAC='00:10:00:00:00:04')
        self.addLink(tn_pe2, pinghost)

        zebraConf = '%s/zebra.conf' % CONFIG_DIR

        # Switches we want to attach our routers to, in the correct order
        attachmentSwitches = [tn_pe1, tn_pe2]
        nRouters = 2
        nHosts = 2

        # Set up the internal BGP speaker
        bgpEth0 = { 'mac':'00:10:0%s:00:02:54' % domID,
                    'ipAddrs' : '10.%s.0.254/24' % domID }
        bgpEth1 = { 'ipAddrs' : '10.10.10.1/24' }
        bgpIntfs = { 'tn-bgp1-eth0' : bgpEth0,
                     'tn-bgp1-eth1' : bgpEth1 }

        ts_bgp1 = { 'remoteMAC' : '00:10:03:00:02:54',
                    'remoteIP' : '10.3.0.254',
                    'remoteMask': '/32',
                    'localdev' : 'tn-bgp1-eth0'}

        #TODO sould be generated!!
        tn_ce1_arp = { 'remoteMAC' : '00:10:02:00:00:01',
                    'remoteIP' : '10.2.0.1',
                    'remoteMask': '/32',
                    'localdev' : 'tn-bgp1-eth0'}

        #TODO sould be generated!!
        tn_ce2_arp = { 'remoteMAC' : '00:10:02:00:00:02',
                    'remoteIP' : '10.2.0.2',
                    'remoteMask': '/32',
                    'localdev' : 'tn-bgp1-eth0'}

        ARPBGPpeers = { 'ts-bgp1' : ts_bgp1,
                        'tn_ce1_arp' : tn_ce1_arp,
                        'tn_ce2_arp' : tn_ce2_arp }

        bgp = self.addHost( "tn-bgp1", cls=Router,
                             quaggaConfFile = '%s/tn-bgp1.conf' % CONFIG_DIR,
                             zebraConfFile = zebraConf,
                             intfDict=bgpIntfs,
                             ARPDict=ARPBGPpeers)


        for i in range(1, nRouters + 1):
            name = 'tn-ce%s' % i

            eth0 = { 'mac' : '00:10:0%s:00:00:0%s' % (domID, i),
                     'ipAddrs' : '10.%s.0.%s/24' % (domID, i),
                     'vlan' : '%s%s' % (domID, i)}
            eth1 = {  'mac' : '00:10:0%s:0%s:02:54' % (domID, i),
                      'ipAddrs' : '10.%s.%s.254/24' % (domID, i)  }

            intfs = { '%s-eth0' % name : eth0,
                      '%s-eth1' % name : eth1 }

            bgpgw = { 'remoteMAC' : bgpEth0['mac'],
                    'remoteIP' : '10.0.0.0',
                    'remoteMask': '/8',
                    'nexthop' : bgpEth0['ipAddrs'].split('/')[0]}

            ARPfakegw = { 'bgpgw' : bgpgw }

            quaggaConf = '%s/tn-ce%s.conf' % (CONFIG_DIR, i)

            router = self.addHost(name, cls=Router, quaggaConfFile=quaggaConf,
                                  zebraConfFile=zebraConf, intfDict=intfs, ARPDict=ARPfakegw)
            self.addLink(router, attachmentSwitches[i-1])

            # learning switch sitting in each customer AS
            # you may need 'sudo apt-get install bridge-utils' for this:
            sw = self.addSwitch('tn-s%s' % i, cls=LinuxBridge)

            for j in range(1, nHosts + 1):
                host = self.addHost('tn-h%s%s' % (i, j), cls=SdnIpHost, ip='10.%s.%s.%s/24' % (domID, i,  j), route='10.%s.%s.254' % (domID, i))
                self.addLink(host, sw)

            self.addLink(router, sw)


        self.addLink( bgp, tn_pc1 )

        # Connect BGP speaker to the root namespace
        root = self.addHost( 'root', inNamespace=False, ip='10.10.10.2/24' )
        self.addLink( root, bgp )



        # Wire up the switches in the topology
        self.addLink( tn_pe1, tn_pc1 )
        self.addLink( tn_pc1, tn_pe2 )
        self.addLink( tn_pe2,tn_gw_ts )

#[PZ] perhaps we will add s4 later; now we want to avoid loop problems
#        self.addLink( s1, s4 )
#        self.addLink( s4, s3 )






class MDCoCoTopoSouth(Topo):
    # TODO : call MDCoCoTopo with domain name parameter
    # we were not successful with
    #def __init__(self, domainname):
    #    Topo.__init__(self, domainname)
    #    self.domainname = domainname

    "Multidomain CoCo topology - TNO South"

    def build( self ):
        domID = 3

        ts_pe1 = self.addSwitch('ts-pe1', dpid='0000000000000001', datapath='user')
#        ts_pc1 = self.addSwitch('ts-pc1', dpid='0000000000000002')
#        ts_pe2 = self.addSwitch('ts-pe2', dpid='0000000000000003')

        pinghost = self.addHost('ts-ph-tn', cls=PingableHost, ip='10.0.0.4/24', mac='00:10:00:00:00:04', remoteIP='10.0.0.3', remoteMAC='00:10:00:00:00:03')
        self.addLink(ts_pe1, pinghost)

        zebraConf = '%s/zebra.conf' % CONFIG_DIR

        # Switches we want to attach our routers to, in the correct order
        attachmentSwitches = [ts_pe1]
        nRouters = 1
        nHosts = 2

        # Set up the internal BGP speaker
        bgpEth0 = { 'mac':'00:10:0%s:00:02:54' % domID,
                    'ipAddrs' : '10.%s.0.254/24' % domID }
        bgpEth1 = { 'ipAddrs' : '10.10.10.1/24' }
        bgpIntfs = { 'ts-bgp1-eth0' : bgpEth0,
                     'ts-bgp1-eth1' : bgpEth1 }


        tn_bgp1 = { 'remoteMAC' : '00:10:02:00:02:54',
                    'remoteIP' : '10.2.0.254',
                    'remoteMask': '/32',
                    'localdev' : 'ts-bgp1-eth0'}

        #TODO sould be generated!!
        ts_ce1_arp = { 'remoteMAC' : '00:10:03:00:00:01',
                    'remoteIP' : '10.3.0.1',
                    'remoteMask': '/32',
                    'localdev' : 'ts-bgp1-eth0'}

        ARPBGPpeers = { 'tn-bgp1' : tn_bgp1,
                        'ts-ce1' :ts_ce1_arp}


        bgp = self.addHost( "ts-bgp1", cls=Router,
                             quaggaConfFile = '%s/ts-bgp1.conf' % CONFIG_DIR,
                             zebraConfFile = zebraConf,
                             intfDict=bgpIntfs,
                             ARPDict=ARPBGPpeers)

        for i in range(1, nRouters + 1):
            name = 'ts-ce%s' % i

            eth0 = { 'mac' : '00:10:0%s:00:00:0%s' % (domID, i),
                     'ipAddrs' : '10.%s.0.%s/24' % (domID, i),
                     'vlan' : '%s%s' % (domID, i)}
            eth1 = {  'mac' : '00:10:0%s:0%s:02:54' % (domID, i),
                      'ipAddrs' : '10.%s.%s.254/24' % (domID, i) }

            intfs = { '%s-eth0' % name : eth0,
                      '%s-eth1' % name : eth1 }

            bgpgw = { 'remoteMAC' : bgpEth0['mac'],
                    'remoteIP' : '10.0.0.0',
                    'remoteMask': '/8',
                    'nexthop' : bgpEth0['ipAddrs'].split('/')[0]} #only ip, get rid of mask

            ARPfakegw = { 'bgpgw' : bgpgw }

            quaggaConf = '%s/ts-ce%s.conf' % (CONFIG_DIR, i)

            router = self.addHost(name, cls=Router, quaggaConfFile=quaggaConf,
                                  zebraConfFile=zebraConf, intfDict=intfs, ARPDict=ARPfakegw)
            self.addLink(router, attachmentSwitches[i-1])

            # learning switch sitting in each customer AS
            # you may need sudo apt-get install bridge-utils for this:
            sw = self.addSwitch('ts-s%s' % i, cls=LinuxBridge)

            for j in range(1, nHosts + 1):
                host = self.addHost('ts-h%s%s' % (i, j), cls=SdnIpHost, ip='10.%s.%s.%s/24' % (domID, i,  j), route='10.%s.%s.254' % (domID, i))
                self.addLink(host, sw)

            self.addLink(router, sw)


        self.addLink( bgp, ts_pe1 )

        # Connect BGP speaker to the root namespace
        root = self.addHost( 'root', inNamespace=False, ip='10.10.10.2/24' )
        self.addLink( root, bgp )



        # Wire up the switches in the topology
        ##for a moment only one switch is present in TNO south
        #self.addLink( ts_pe1, ts_pc1 )
        #self.addLink( ts_pc1, ts_pe2 )



topos = { 'tnonorth' : MDCoCoTopoNorth,
          'tnosouth' : MDCoCoTopoSouth }

if __name__ == '__main__':
    setLogLevel('debug')
    topo = MDCoCoTopoNorth()
    #topo = MDCoCoTopoSouth()

    net = Mininet(topo=topo, controller=RemoteController)
    #hp = net.hosts[-1]
    #info(hp)
    # aww how ugly
    #if hp.name[0:2] == 'ts':
    #    hp.setARP('10.0.0.3', '00:10:00:00:00:03')
    #if hp.name[0:2] == 'tn':
    #    hp.setARP('10.0.0.4', '00:10:00:00:00:04')

    net.start()

    #hp.cmd('arp -s 10.0.0.4 00:10:00:00:00:04')

    CLI(net)

    net.stop()

    info("done\n")

#topos = { 'tnonorth': ( lambda: MDCoCoTopoNorth() ),
#          'tnosouth': ( lambda: MDCoCoTopoSouth() ) }

#topos = { 'cocotopo': ( lambda: CoCoTopo() ) }
