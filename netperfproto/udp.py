import time
import struct
from dataclasses import dataclass
from collections import deque
import datetime
from typing import Callable, Deque, Optional
import asyncio
from netperfbackend.models import UdpMetricPoint


async def udp_server(port: int):
    class EchoProto(asyncio.DatagramProtocol):
        def connection_made(self, transport: asyncio.DatagramTransport):
            self.transport = transport

        def datagram_received(self, data, addr):
            self.transport.sendto(data, addr)

    loop = asyncio.get_running_loop()

    t, p = await loop.create_datagram_endpoint(
        lambda: EchoProto(), local_addr=("0.0.0.0", port)
    )

    while True:
        await asyncio.sleep(10)


UdpMetricCallback = Callable[[UdpMetricPoint], None]


def udp_client(
    data_cb: UdpMetricCallback,
    host: str,
    port: int,
    duration: datetime.timedelta,
):
    @dataclass
    class RxPacket:
        seq_no: int
        tx_time: int
        rx_time: int

    class UdpTelemetryProto(asyncio.DatagramProtocol):
        # send packet every 50ms
        # queue 150 rx packets
        # every 1s, process rx queue and push metrics
        def __init__(self, cb: UdpMetricCallback):
            self.loop = asyncio.get_running_loop()
            self.cb = cb
            self.transport = None
            self.prior_seq_no = -1
            self.next_seq_no = 0
            self.rx_queue: Deque[RxPacket] = deque(maxlen=250)

        def connection_lost(self, exc):
            if self.send_callback_handle:
                self.send_callback_handle.cancel()
                self.send_callback_handle = None
            if self.metrics_callback_handle:
                self.metrics_callback_handle.cancel()
                self.metrics_callback_handle = None

        def schedule_send(self, delay: Optional[float] = None):
            if delay:
                self.send_callback_handle = self.loop.call_later(
                    delay, UdpTelemetryProto.send_packet, self
                )
            else:
                self.send_callback_handle = self.loop.call_soon(self.send_packet)

        def schedule_metrics(self):
            self.metrics_callback_handle = self.loop.call_later(1, self.compute_metrics)

        def connection_made(self, transport: asyncio.DatagramTransport):
            self.transport = transport

            self.schedule_send()
            self.schedule_metrics()

        def send_packet(self):
            seq_no = self.next_seq_no
            time_us = time.time_ns() // 1000
            b = struct.pack("!qq", seq_no, time_us)

            self.transport.sendto(b)

            # send next seq no in 50ms
            self.next_seq_no += 1
            self.schedule_send(0.05)

        def compute_metrics(self):
            cur_time_us = time.time_ns() // 1000
            min_rx_time = cur_time_us - 5 * 1_000_000
            recent_packets = list(
                [p for p in self.rx_queue if p.rx_time >= min_rx_time]
            )
            num_recent_packets = len(recent_packets)

            latency_ms = 5000.0
            loss = 100.0
            if num_recent_packets > 0:
                latency_sum = 0
                for p in recent_packets:
                    latency_sum += p.rx_time - p.tx_time
                latency = float(latency_sum) / len(recent_packets)
                latency_ms = latency / 1_000.0

            if num_recent_packets > 1:
                """
                3 4 5 6
                1 + (6 - 3) = 4 << denominator
                4 - 4 = 0 << numerator
                0 / 4 packets lost

                3 6
                1 + (6 - 3) = 4 << denominator
                4 - 2 = 2 << numerator
                2 / 4 packets lost
                """
                seq_numbers = sorted(
                    [p.seq_no for p in self.rx_queue if p.seq_no > self.prior_seq_no]
                )
                expected_len = seq_numbers[-1] - self.prior_seq_no
                packets_lost = expected_len - len(seq_numbers)
                self.prior_seq_no = seq_numbers[-1]
                loss = (100.0 * packets_lost) / expected_len

            cur_time = datetime.datetime.now()

            self.schedule_metrics()

            self.cb(
                UdpMetricPoint(timestamp=cur_time, loss=loss, latency=latency_ms),
            )

        def datagram_received(self, data, addr):
            seq_no, tx_time_us = struct.unpack("!qq", data)
            rx_time_us = time.time_ns() // 1000

            self.rx_queue.appendleft(RxPacket(seq_no, tx_time_us, rx_time_us))

    async def runner():
        nonlocal data_cb, host, port, duration

        transport = None

        try:
            (
                transport,
                protocol,
            ) = await asyncio.get_running_loop().create_datagram_endpoint(
                lambda: UdpTelemetryProto(data_cb), remote_addr=(host, port)
            )

            await asyncio.sleep(duration.total_seconds())
        except asyncio.CancelledError:
            pass
        finally:
            if transport:
                transport.abort()

    return asyncio.create_task(runner())
