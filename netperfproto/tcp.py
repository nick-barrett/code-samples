import datetime
import asyncio
from asyncio import Task
from typing import Callable, Optional
from netperfbackend.models import TcpMetricPoint


# TODO: Add support for receiving data, not only sending
async def tcp_server(port: int):
    buf = bytearray(65536)
    for i in range(len(buf)):
        buf[i] = i % 256

    class FloodProto(asyncio.Protocol):
        def __init__(self):
            self.loop = asyncio.get_running_loop()
            self.slow_down = False

        def schedule_send(self, delay: Optional[float] = None):
            if delay:
                self.callback_handle = self.loop.call_later(
                    delay, FloodProto.send_buf, self
                )
            else:
                self.callback_handle = self.loop.call_soon(FloodProto.send_buf, self)

        def cancel_send(self):
            if self.callback_handle:
                self.callback_handle.cancel()
                self.callback_handle = None

        def connection_made(self, transport: asyncio.Transport):
            self.transport = transport
            self.transport.set_write_buffer_limits(low=2**16, high=2**19)

            self.slow_down = False
            self.schedule_send()

        def send_buf(self):
            self.transport.write(buf)
            if not self.slow_down:
                self.schedule_send()

        def resume_writing(self):
            self.slow_down = False
            self.schedule_send()

        def pause_writing(self):
            self.slow_down = True

        def connection_lost(self, exc: Exception | None):
            self.slow_down = True
            self.cancel_send()

    loop = asyncio.get_running_loop()
    server = await loop.create_server(lambda: FloodProto(), host="0.0.0.0", port=port)

    async with server:
        await server.serve_forever()


TcpMetricCallback = Callable[[TcpMetricPoint], None]


# TODO: Add support for sending data, not only receiving
def tcp_client(
    cb: TcpMetricCallback, host: str, port: int, duration: datetime.timedelta
) -> Task[None]:
    buf = bytearray(65536)

    tx_buf = bytearray(65536)
    for i in range(len(tx_buf)):
        tx_buf[i] = (i + 10) % 256

    class FloodRxProto(asyncio.BufferedProtocol):
        def __init__(self, cb: TcpMetricCallback):
            self.loop = asyncio.get_running_loop()
            self.cb = cb

        def cancel_tick(self):
            if self.callback_handle:
                self.callback_handle.cancel()
                self.callback_handle = None

        def schedule_tick(self):
            self.callback_handle = self.loop.call_later(1, self.tick)

        def connection_made(self, transport: asyncio.Transport):
            self.transport = transport

            self.byte_count = 0
            self.interval_start = datetime.datetime.now()
            self.schedule_tick()

        def tick(self):
            current_time = datetime.datetime.now()
            delta_time = (current_time - self.interval_start).total_seconds()

            # avoid divide by small number
            if delta_time > 0.5:
                mbits_per_second = (8.0 * self.byte_count) / (delta_time * 1_000_000)
                self.schedule_tick()

                try:
                    self.cb(
                        TcpMetricPoint(timestamp=current_time, rate=mbits_per_second)
                    )

                    self.byte_count = 0
                    self.interval_start = current_time
                except Exception:
                    return

        def connection_lost(self, exc):
            self.cancel_tick()

        def get_buffer(self, sizehint: int):
            return buf

        def buffer_updated(self, nbytes: int):
            self.byte_count += nbytes

    loop = asyncio.get_running_loop()

    async def runner():
        nonlocal cb, host, port, duration

        transport = None

        try:
            transport, protocol = await loop.create_connection(
                lambda: FloodRxProto(cb),
                host,
                port,
            )

            await asyncio.sleep(duration.total_seconds())
        except asyncio.CancelledError:
            pass
        finally:
            if transport:
                transport.abort()

    return asyncio.create_task(runner())
