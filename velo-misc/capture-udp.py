"""
Capture UDP packets and write them to a file as length-prefixed raw binary data.
This was used for NetFlow analysis, but can be used for any UDP-based protocol.
"""


import asyncio
import datetime
import struct
from typing import List

def do_flush_buffers(buffers: List[bytes]) -> int:
    with open("udp-dump.bin", "ab") as f:
        for buf in buffers:
            f.write(struct.pack("!h", len(buf)))
            f.write(buf)

    return len(buffers)

async def udp_server(port: int):
    class EchoProto(asyncio.DatagramProtocol):
        def __init__(self):
            self.buffers = []
            self.loop = asyncio.get_running_loop()

            self.schedule_flush()

        def schedule_flush(self):
            loop.call_later(30, self.flush_buffers)

        def flush_buffers(self):
            self.loop.run_in_executor(None, do_flush_buffers, self.buffers).add_done_callback(self.flush_buffers_done)
            self.buffers = []
            self.schedule_flush()

        def flush_buffers_done(self, future: asyncio.Future[int]):
            print("Flushed {} buffers at {}".format(future.result(), datetime.datetime.now()))

        def connection_made(self, transport: asyncio.DatagramTransport):
            self.transport = transport

        def datagram_received(self, data, addr):
            self.buffers.append(data)

    loop = asyncio.get_running_loop()

    t, p = await loop.create_datagram_endpoint(
        lambda: EchoProto(), local_addr=("0.0.0.0", port)
    )

    while True:
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(udp_server(4739))