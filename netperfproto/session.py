from asyncio import Event
import asyncio
from typing import Dict, Optional
import uuid

from netperfbackend.models import (
    BackendControlMessage,
    BackendRegisterClientNode,
    BackendSessionCreate,
    BackendSessionDestroy,
    BackendSessionEnded,
    BackendSessionMetric,
    SessionMetricTcp,
    SessionMetricUdp,
)
from control import ControlProtocol

from udp import udp_client
from tcp import tcp_client


class SessionManager:
    def __init__(self, name: str, control: ControlProtocol, stop_event: Event):
        self.id = uuid.uuid4()
        self.name = name
        self.control = control
        self.stop_event = stop_event

        self.task: Optional[asyncio.Task] = None

    def run(self):
        async def runner(
            control: ControlProtocol,
            stop_event: Event,
        ):
            sessions: Dict[uuid.UUID, Optional[asyncio.Task]] = {}

            stop_recv = asyncio.create_task(stop_event.wait())

            def conn_est_factory():
                return asyncio.create_task(control.wait_for_conn_established())

            def msg_recv_factory():
                return asyncio.create_task(control.recv_message())

            def register_timer_factory():
                return asyncio.create_task(asyncio.sleep(5))

            conn_est = conn_est_factory()
            msg_recv = msg_recv_factory()
            register_timer = register_timer_factory()

            fut_set = set((stop_recv, conn_est, msg_recv, register_timer))

            while True:
                done, pending = await asyncio.wait(
                    fut_set, return_when=asyncio.FIRST_COMPLETED
                )

                for f in done:
                    if f == stop_recv:
                        # TODO: cancellations
                        for s in sessions.values():
                            if s:
                                s.cancel()
                        return
                    elif f == register_timer:
                        await register_timer
                        await control.send_message(
                            BackendRegisterClientNode(id=self.id, name=self.name)
                        )

                        register_timer = register_timer_factory()
                        pending.add(register_timer)
                    elif f == conn_est:
                        _ = await conn_est

                        await control.send_message(
                            BackendRegisterClientNode(id=self.id, name=self.name)
                        )
                        control.clear_conn_established()

                        conn_est = conn_est_factory()
                        pending.add(conn_est)
                    elif f == msg_recv:
                        msg = await msg_recv
                        match msg:
                            case BackendControlMessage(
                                data=BackendSessionCreate(
                                    session_id=session_id,
                                    target_service=target_service,
                                    duration=duration,
                                )
                            ):
                                match target_service.scheme:
                                    case "tcp":

                                        def metric_cb(
                                            pt, control=control, session_id=session_id
                                        ):
                                            control.send_message_nowait(
                                                BackendSessionMetric(
                                                    session_id=session_id,
                                                    data=SessionMetricTcp(pt=pt),
                                                )
                                            )

                                        tcp_task = tcp_client(
                                            metric_cb,
                                            target_service.host,
                                            target_service.port,
                                            duration,
                                        )

                                        sessions[session_id] = tcp_task

                                        def session_ended_msg_cb(
                                            t, control=control, session_id=session_id
                                        ):
                                            control.send_message_nowait(
                                                BackendSessionEnded(
                                                    session_id=session_id
                                                )
                                            )

                                        def remove_session_task_cb(
                                            t, sessions=sessions, session_id=session_id
                                        ):
                                            sessions.pop(session_id, None)

                                        tcp_task.add_done_callback(session_ended_msg_cb)
                                        tcp_task.add_done_callback(
                                            remove_session_task_cb
                                        )

                                    case "udp":

                                        def metric_cb(
                                            pt, control=control, session_id=session_id
                                        ):
                                            control.send_message_nowait(
                                                BackendSessionMetric(
                                                    session_id=session_id,
                                                    data=SessionMetricUdp(pt=pt),
                                                )
                                            )

                                        udp_task = udp_client(
                                            metric_cb,
                                            target_service.host,
                                            target_service.port,
                                            duration,
                                        )

                                        sessions[session_id] = udp_task

                                        def session_ended_msg_cb(
                                            t, control=control, session_id=session_id
                                        ):
                                            control.send_message_nowait(
                                                BackendSessionEnded(
                                                    session_id=session_id
                                                )
                                            )

                                        def remove_session_task_cb(
                                            t, sessions=sessions, session_id=session_id
                                        ):
                                            sessions.pop(session_id, None)

                                        udp_task.add_done_callback(session_ended_msg_cb)
                                        udp_task.add_done_callback(
                                            remove_session_task_cb
                                        )
                                    case _:
                                        pass
                            case BackendControlMessage(
                                data=BackendSessionDestroy(session_id=session_id)
                            ):
                                if session_id in sessions:
                                    sessions[session_id].cancel()
                            case _:
                                pass

                        msg_recv = msg_recv_factory()
                        pending.add(msg_recv)

                fut_set = pending

        self.task = asyncio.create_task(runner(self.control, self.stop_event))

    async def wait(self):
        if self.task:
            await self.task
