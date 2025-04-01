use crate::PacketDirection;

pub struct UdpHostStats {}

impl UdpHostStats {
    pub fn new() -> Self {
        Self {}
    }
}

pub enum UdpState {
    Init,
}

pub struct UdpSession {
    client_stats: UdpHostStats,
    server_stats: UdpHostStats,

    state: UdpState,
}

impl UdpSession {
    pub fn new() -> Self {
        UdpSession {
            client_stats: UdpHostStats::new(),
            server_stats: UdpHostStats::new(),
            state: UdpState::Init,
        }
    }

    pub fn process_packet(&mut self, buffer: &[u8], direction: PacketDirection) {
        match direction {
            PacketDirection::ClientToServer => {}
            PacketDirection::ServerToClient => {}
        }
    }
}
