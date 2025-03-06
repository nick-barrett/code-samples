from pysnmp.hlapi import (
    bulkCmd,
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
)

import time

"""
Setup:
- pip install pysnmplib==5.0.20
- mibdump.py --mib-source=~/.snmp/mibs --mib-source=/usr/share/snmp/mibs VELOCLOUD-MIB VELOCLOUD-EDGE-MIB
  - This command comes from the pysmi package. It may need to be installed and its path fully qualified.
  - This will generate compiled files for pysnmp to use when working with SD-WAN edge SNMP queries
- Ensure that VELOCLOUD-MIB.py & VELOCLOUD-EDGE-MIB.py exist in the ~/.pysnmp/mibs directory.

Running:
- python snmp-demo.py

Sample output:
VELOCLOUD-EDGE-MIB::vceLinkName."03-6270-460e-bf22-3671b1e2c020" = Spectrum         <-- Link 1 name
VELOCLOUD-EDGE-MIB::vceLinkTotTxbytes."03-6270-460e-bf22-3671b1e2c020" = 2101588820 <-- Link 1 TX bytes
VELOCLOUD-EDGE-MIB::vceLinkTotRxBytes."03-6270-460e-bf22-3671b1e2c020" = 8363068293 <-- Link 1 RX bytes
VELOCLOUD-EDGE-MIB::vceLinkName."04-6270-460e-bf22-3671b1e2c020" = T-Mobile USA     <-- Link 2 name
VELOCLOUD-EDGE-MIB::vceLinkTotTxbytes."04-6270-460e-bf22-3671b1e2c020" = 485080296  <-- Link 2 TX Bytes
VELOCLOUD-EDGE-MIB::vceLinkTotRxBytes."04-6270-460e-bf22-3671b1e2c020" = 346077811  <-- Link 2 RX Bytes

The edge SNMP database updates once every 60 seconds, so don't poll more frequently than that.
"""

for i in range(1000):
    iterator = bulkCmd(
        SnmpEngine(),
        CommunityData("velocl0ud"),
        UdpTransportTarget(("172.16.142.1", 161), timeout=5),
        ContextData(),
        0,
        25,
        ObjectType(
            ObjectIdentity("VELOCLOUD-EDGE-MIB", "vceLinkName").addMibSource(
                "~/.pysnmp/mibs"
            )
        ),
        ObjectType(
            ObjectIdentity("VELOCLOUD-EDGE-MIB", "vceLinkItf").addMibSource(
                "~/.pysnmp/mibs"
            )
        ),
        ObjectType(
            ObjectIdentity("VELOCLOUD-EDGE-MIB", "vceLinkTotTxbytes").addMibSource(
                "~/.pysnmp/mibs"
            )
        ),
        ObjectType(
            ObjectIdentity("VELOCLOUD-EDGE-MIB", "vceLinkTotRxBytes").addMibSource(
                "~/.pysnmp/mibs"
            )
        ), # additional link data could be gathered similarly to this. Reference VELOCLOUD-EDGE-MIB for other names.
        lexicographicMode=False,
    )

    for errorIndication, errorStatus, errorIndex, varBinds in iterator:
        if errorIndication:
            print(errorIndication)
            break

        elif errorStatus:
            print(
                "{} at {}".format(
                    errorStatus.prettyPrint(),
                    errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
                )
            )
            break

        else:
            for varBind in varBinds:
                print(" = ".join([x.prettyPrint() for x in varBind]))

    time.sleep(60)
