import asyncio
from datetime import datetime, timedelta
from typing import Tuple
import aiohttp
import dotenv
import ijson
from veloapi.models import CommonData
from veloapi.util import read_env

"""

This is a WIP. See veloapi/api.py#get_edge_flow_visibility_metrics_fast for a better example of using ijson.

The edge computes 5-minute aggregates metrics and sends them to the VCO.
VCO backlogs these metrics and processes them in batches.
Periodically, the VCO consumes metrics and inserts them into the DB.

Link stats table:
- partitioned over time
- ordered by
    - enterpriseLogicalId
    - edgeLogicalId
    - hour
    - linkLogicalId

Each link row:
{
        'linkLogicalId': 'c487d5bc-f2ce-485d-a4df-76dfcdae5105', 
        'edgeLogicalId': '1627a716-7bda-4602-b6db-6288aef7eb45', 
        'bytesTx': 833945, 
        'bytesRx': 620871, 
        'packetsTx': 9177, 
        'packetsRx': 8168, 
        'totalBytes': 1454816, 
        'totalPackets': 17345, 
        'p1BytesRx': 29149, 
        'p1BytesTx': 98586, 
        'p1PacketsRx': 144, 
        'p1PacketsTx': 310, 
        'p2BytesRx': 0, 
        'p2BytesTx': 0, 
        'p2PacketsRx': 0, 
        'p2PacketsTx': 0, 
        'p3BytesRx': 0, 
        'p3BytesTx': 0, 
        'p3PacketsRx': 0, 
        'p3PacketsTx': 0, 
        'controlBytesRx': 591722, 
        'controlBytesTx': 735359, 
        'controlPacketsRx': 8024, 
        'controlPacketsTx': 8867, 
        'bpsOfBestPathRx': 50000000, 
        'bpsOfBestPathTx': 5000000, 
        'bestJitterMsRx': 0, 
        'bestJitterMsTx': Decimal('1.5'), 
        'bestLatencyMsRx': Decimal('78.5'), 
        'bestLatencyMsTx': 2, 
        'bestLossPctRx': 0, 
        'bestLossPctTx': 0, 
        'scoreTx': Decimal('4.400000095367432'), 
        'scoreRx': Decimal('4.360000133514404'), 
        'signalStrength': 0, 
        'state': 'STABLE', 
        'autoDualMode': '', 
        'name': 'GE4', 
        'link': {
                'enterpriseName': 'NBarrett-Lab-vco12', 
                'enterpriseId': 3480, 
                'enterpriseProxyId': 69, 
                'enterpriseProxyName': 'Barrett_Partner_Lab', 
                'edgeName': 'Home-Edge-710', 
                'edgeState': 'CONNECTED', 
                'edgeSystemUpSince': '2024-06-26T17:17:20.000Z', 
                'edgeServiceUpSince': '2024-06-26T17:18:48.000Z', 
                'edgeLastContact': '2024-08-05T22:21:39.000Z', 
                'edgeId': 41838, 
                'edgeSerialNumber': 'VC07102337000139', 
                'edgeHASerialNumber': None, 
                'edgeModelNumber': 'edge710', 
                'edgeLatitude': Decimal('38.59'), 
                'edgeLongitude': Decimal('-89.906631'), 
                'enterpriseLogicalId': '208e812f-24dd-4531-8371-d99ed4d0dd00', 
                'edgeCreated': '2024-04-17T15:29:21.000Z', 
                'edgeModified': '2024-08-05T22:22:00.000Z', 
                'edgeLogicalId': '1627a716-7bda-4602-b6db-6288aef7eb45', 
                'activationTime': '2024-06-26T16:49:18.000Z', 
                'softwareVersion': '5.4.0.0', 
                'buildNumber': 'R5400-20231230-GA-134893-3c6e4f5c0f', 
                'softwareUpdated': '2024-06-26T17:18:50.000Z', 
                'isLive': 0, 
                'siteId': 42045, 
                'activationState': 'ACTIVATED', 
                'factorySoftwareVersion': '5.2.1.0', 
                'factoryBuildNumber': 'R5210-20230803-MR-GA', 
                'timezone': 'America/Chicago', 
                'displayName': 'Spectrum (Impaired)', 
                'isp': '', 
                'interface': 'GE4', 
                'internalId': 'c487d5bc-f2ce-485d-a4df-76dfcdae5105', 
                'linkState': 'STABLE', 
                'linkLastActive': '2024-08-06T15:35:20.000Z', 
                'linkVpnState': 'STABLE', 
                'linkId': 32533, 
                'linkIpAddress': '75.132.173.180', 
                'linkIpV6Address': '', 
                'linkMode': 'ACTIVE', 
                'linkBackupState': 'UNCONFIGURED', 
                'linkCreated': '2024-06-26T16:54:29.000Z', 
                'linkModified': '2024-08-06T15:35:20.000Z', 
                'linkLogicalId': 'c487d5bc-f2ce-485d-a4df-76dfcdae5105'
        }, 
        'linkId': 32533
}

INSTALL spatial;
LOAD spatial;

CREATE TABLE links (
    enterpriseLogicalId UUID,
    edgeLogicalId UUID,
    linkLogicalId UUID,
    enterpriseId UINTEGER,
    edgeId UINTEGER,
    linkId UINTEGER,
    interface TEXT,
    ipAddress INET,
    ipV6Address INET,
    displayName TEXT,
    isp TEXT
);

CREATE TABLE linkstats (
    timestamp TIMESTAMP,
    enterpriseLogicalId UUID,
    edgeLogicalId UUID,
    linkLogicalId UUID,
    bytesTx UBIGINT,
    bytesRx UBIGINT,
    packetsTx UBIGINT,
    packetsRx UBIGINT,
    totalBytes UBIGINT,
    totalPackets UBIGINT,
    p1BytesRx UBIGINT,
    p1BytesTx UBIGINT,
    p1PacketsRx UBIGINT,
    p1PacketsTx UBIGINT,
    p2BytesRx UBIGINT,
    p2BytesTx UBIGINT,
    p2PacketsRx UBIGINT,
    p2PacketsTx UBIGINT,
    p3BytesRx UBIGINT,
    p3BytesTx UBIGINT,
    p3PacketsRx UBIGINT,
    p3PacketsTx UBIGINT,
    controlBytesRx UBIGINT,
    controlBytesTx UBIGINT,
    controlPacketsRx UBIGINT,
    controlPacketsTx UBIGINT,
    bpsOfBestPathRx UBIGINT,
    bpsOfBestPathTx UBIGINT,
    bestJitterMsRx UINTEGER,
    bestJitterMsTx UINTEGER,
    bestLatencyMsRx UINTEGER,
    bestLatencyMsTx UINTEGER,
    bestLossPctRx FLOAT,
    bestLossPctTx FLOAT,
    scoreTx FLOAT,
    scoreRx FLOAT,
    signalStrength FLOAT,
    state TEXT,
    autoDualMode TEXT
);

"""


def make_request(c: CommonData, start: datetime, end: datetime) -> Tuple[str, dict]:
    return (
        f"https://{c.vco}/portal/",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "monitoring/getAggregateEdgeLinkMetrics",
            "params": {
                "enterpriseId": c.enterprise_id,
                "interval": {
                    "start": int(start.timestamp() * 1000),
                    "end": int(end.timestamp() * 1000),
                }
            },
        },
    )


async def main(c: CommonData):
    start = datetime.now() - timedelta(minutes=20)
    # this would be the timestamp of the record
    timestamp = start + timedelta(minutes=5)  # noqa: F841
    end = start + timedelta(minutes=10)

    (url, body) = make_request(c, start, end)

    async with c.session.post(url, json=body) as response:
        async for link in ijson.items_async(response.content, "result.item"):
            pass


async def async_main():
    async with aiohttp.ClientSession() as session:
        await main(
            CommonData(
                read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
            )
        )


if __name__ == "__main__":
    dotenv.load_dotenv("env/.env", verbose=True, override=True)
    asyncio.run(async_main())
