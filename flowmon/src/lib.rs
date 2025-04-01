/*

- Ingress-agnostic - PCAP, SPAN, GENEVE, etc.
- Should provide method to use external session keys
  - AWS GWLB GENEVE header provides a cookie
- Monitor performance of network conversations
- Export performance data in real-time
- Protocols:
  - UDP
    - DNS
      - (timestamp, source-ip, server-ip, rec-type, rec-name, status, latency)
    - RADIUS
      - ?
    - SIP
    - RTP + RTCP
  - TCP
    - HTTP
    - TLS
    - DNS
    - SIP

*/

use std::{collections::HashMap, hash::Hash};

mod tcp;
mod udp;

pub enum PacketDirection {
    ClientToServer,
    ServerToClient,
}

pub struct TcpFlags(u8);

impl TcpFlags {
    pub fn new(flags: u8) -> Self {
        Self(flags)
    }

    pub fn is_syn(&self) -> bool {
        self.0 & 0x02 != 0
    }

    pub fn is_ack(&self) -> bool {
        self.0 & 0x10 != 0
    }

    pub fn is_fin(&self) -> bool {
        self.0 & 0x01 != 0
    }
}

pub struct IPv4Flags(u8);

impl IPv4Flags {
    pub fn new(flags: u8) -> Self {
        Self(flags)
    }

    pub fn is_more_fragments(&self) -> bool {
        self.0 & 0x01 != 0
    }

    pub fn is_dont_fragment(&self) -> bool {
        self.0 & 0x02 != 0
    }
}

pub enum NetworkMeta {
    Pending,
    IPv4Fragment {
        source_ip: u32,
        destination_ip: u32,
        identifier: u16,
        flags: IPv4Flags,
        offset: usize,
    },
    IPv4 {
        source_ip: u32,
        destination_ip: u32,
        flags: IPv4Flags,
    },
    Unknown,
}

pub enum TransportMeta {
    Pending,
    TCP {
        source_port: u16,
        destination_port: u16,
        flags: TcpFlags,
    },
    UDP {
        source_port: u16,
        destination_port: u16,
    },
    Other {
        protocol: u8,
    },
}

pub struct PacketMeta<'a> {
    pub timestamp: u64,
    pub network: NetworkMeta,
    pub transport: TransportMeta,
    pub payload: &'a [u8],
}

impl<'a> PacketMeta<'a> {
    pub fn new(
        packet: &'a [u8],
        timestamp: u64,
    ) -> Self {
        Self {
            timestamp,
            network: NetworkMeta::Pending,
            transport: TransportMeta::Pending,
            payload: packet,
        }
    }
}

pub struct SessionTuple {
    pub client_ip: u32,
    pub server_ip: u32,
    pub client_port: u16,
    pub server_port: u16,
    pub protocol: u8,
}

impl SessionTuple {
    pub fn new(
        client_ip: u32,
        server_ip: u32,
        client_port: u16,
        server_port: u16,
        protocol: u8,
    ) -> Self {
        Self {
            client_ip,
            server_ip,
            client_port,
            server_port,
            protocol,
        }
    }
}

/// A key for a session that is used to identify the session in a hash table.
/// The IP addresses are used to sort the IPs and ports, so that the key can be used bi-directionally.
#[derive(PartialEq, Eq, Hash)]
pub struct SessionKey {
    pub lesser_ip: u32,
    pub greater_ip: u32,
    pub lesser_port: u16,
    pub greater_port: u16,
    pub protocol: u8,
}

impl SessionKey {
    pub fn new(
        source_ip: u32,
        destination_ip: u32,
        source_port: u16,
        destination_port: u16,
        protocol: u8,
    ) -> Self {
        let (lesser_ip, lesser_port, greater_ip, greater_port) = if source_ip < destination_ip {
            (source_ip, source_port, destination_ip, destination_port)
        } else {
            (destination_ip, destination_port, source_ip, source_port)
        };

        Self {
            lesser_ip,
            greater_ip,
            lesser_port,
            greater_port,
            protocol,
        }
    }
}

pub struct SessionStats {
    pub packets_rx: u64,
    pub packets_tx: u64,
    pub bytes_rx: u64,
    pub bytes_tx: u64,
}

pub enum SessionInfo {
    Pending,
    Http {
        method: String,
        uri: String,
        status_code: u16,
        response_time: u64,
    },
    Dns {
        query: String,
        response: String,
        status: u16,
        latency: u64,
    },
}

pub enum TransportSession {
    Tcp(tcp::TcpSession),
    Udp(udp::UdpSession),
    Other,
}

pub struct Session {
    pub tuple: SessionTuple,
    pub start_time: u64,
    pub last_tx_time: u64,
    pub last_rx_time: u64,
    pub stats: SessionStats,
    pub info: SessionInfo,
    pub transport: TransportSession,
}

impl Session {
    pub fn new(tuple: SessionTuple, stats: SessionStats) -> Self {
        let transport = match tuple.protocol {
            6 => TransportSession::Tcp(tcp::TcpSession::new()),
            17 => TransportSession::Udp(udp::UdpSession::new()),
            _ => TransportSession::Other,
        };

        Self {
            tuple,
            start_time: 0,
            last_tx_time: 0,
            last_rx_time: 0,
            stats,
            info: SessionInfo::Pending,
            transport,
        }
    }

    pub fn key(&self) -> SessionKey {
        SessionKey::new(
            self.tuple.client_ip,
            self.tuple.server_ip,
            self.tuple.client_port,
            self.tuple.server_port,
            self.tuple.protocol,
        )
    }

    pub fn handle(&mut self, direction: PacketDirection, payload: &[u8]) {
        match direction {
            PacketDirection::ServerToClient => {
                self.stats.packets_rx += 1;
                self.stats.bytes_rx += payload.len() as u64;
                self.last_rx_time = 0; // TODO: set to current time
            }
            PacketDirection::ClientToServer => {
                self.stats.packets_tx += 1;
                self.stats.bytes_tx += payload.len() as u64;
                self.last_tx_time = 0; // TODO: set to current time
            }
        }

        match &mut self.transport {
            TransportSession::Tcp(session) => {
                session.process_packet(payload, direction);
            },
            TransportSession::Udp(session) => {
                session.process_packet(payload, direction);
            }
            _ => {}
        }
    }

    #[inline]
    pub fn pkt_direction(&self, source_ip: u32) -> PacketDirection {
        if source_ip == self.tuple.client_ip {
            PacketDirection::ClientToServer
        } else {
            PacketDirection::ServerToClient
        }
    }
}

pub struct FlowMon {
    sessions: HashMap<SessionKey, Session>,
    // TODO: object pool to cache stat objects for each type
}

impl FlowMon {
    pub fn new() -> Self {
        Self {
            sessions: HashMap::new(),
        }
    }

    fn handle_ipv4_fragmentation(
        &mut self,
        ip_hdr: &[u8],
        more_fragments: bool,
        scaled_fragment_offset: usize,
        transport_data: &[u8],
    ) {
        let total_length: u16 = u16::from_be_bytes(ip_hdr[2..4].try_into().unwrap());
        let identification: u16 = u16::from_be_bytes(ip_hdr[4..6].try_into().unwrap());

        // Handle IPv4 fragmentation
        // Check if the packet is fragmented and reassemble it if necessary
        // Store the reassembled packet in a buffer for further processing
        // If it's not fragmented, process the packet normally
    }

    fn handle_ipv4_udp_packet(
        &mut self,
        source_address: [u8; 4],
        destination_address: [u8; 4],
        transport_data: &[u8],
    ) {
        let udp_header_length: usize = 8;

        if transport_data.len() < udp_header_length {
            return;
        }

        let source_port = u16::from_be_bytes([transport_data[0], transport_data[1]]);
        let destination_port = u16::from_be_bytes([transport_data[2], transport_data[3]]);

        let source_ip = u32::from_be_bytes(source_address);
        let destination_ip = u32::from_be_bytes(destination_address);

        let length = u16::from_be_bytes([transport_data[4], transport_data[5]]) as usize;

        if transport_data.len() < length {
            return;
        }

        let key = SessionKey::new(source_ip, destination_ip, source_port, destination_port, 17);

        let session = self.sessions.entry(key).or_insert_with(|| {
            Session::new(
                SessionTuple::new(source_ip, destination_ip, source_port, destination_port, 17),
                SessionStats {
                    packets_rx: 0,
                    packets_tx: 0,
                    bytes_rx: 0,
                    bytes_tx: 0,
                },
            )
        });

        let direction = session.pkt_direction(source_ip);

        session.handle(direction, &transport_data[..length]);
    }

    fn handle_ipv4_tcp_packet(
        &mut self,
        source_address: [u8; 4],
        destination_address: [u8; 4],
        transport_data: &[u8],
    ) {
        let tcp_header_length: usize = 20;
        if transport_data.len() < tcp_header_length {
            return;
        }

        let source_port = u16::from_be_bytes([transport_data[0], transport_data[1]]);
        let destination_port = u16::from_be_bytes([transport_data[2], transport_data[3]]);

        let source_ip = u32::from_be_bytes(source_address);
        let destination_ip = u32::from_be_bytes(destination_address);

        let key = SessionKey::new(source_ip, destination_ip, source_port, destination_port, 6);

        let session = self.sessions.entry(key).or_insert_with(|| {
            Session::new(
                SessionTuple::new(source_ip, destination_ip, source_port, destination_port, 6),
                SessionStats {
                    packets_rx: 0,
                    packets_tx: 0,
                    bytes_rx: 0,
                    bytes_tx: 0,
                },
            )
        });

        let direction = session.pkt_direction(source_ip);

        session.handle(direction, transport_data);
    }

    fn handle_ipv4_packet(&mut self, ip_hdr: &[u8], transport_data: &[u8]) {
        let flags: u8 = ip_hdr[6] >> 5;
        let more_fragments = flags & 0x1 != 0;
        let unscaled_fragment_offset: usize =
            (u16::from_be_bytes([ip_hdr[6], ip_hdr[7]]) & 0x1FFF) as usize;

        if more_fragments || unscaled_fragment_offset != 0 {
            self.handle_ipv4_fragmentation(
                ip_hdr,
                more_fragments,
                8 * unscaled_fragment_offset,
                transport_data,
            );
            return;
        }

        let proto = ip_hdr[9];

        let source_address: [u8; 4] = ip_hdr[12..16].try_into().unwrap();
        let destination_address: [u8; 4] = ip_hdr[16..20].try_into().unwrap();

        match proto {
            17 => {
                self.handle_ipv4_udp_packet(source_address, destination_address, transport_data);
            }
            6 => {
                self.handle_ipv4_tcp_packet(source_address, destination_address, transport_data);
            }
            _ => {
                // Unsupported protocol
            }
        }
    }

    pub fn handle_ipvx_packet(&mut self, packet: &[u8]) {
        if packet.len() < 28 {
            // minimum length is 28 bytes - 20 bytes for IP header and 8 bytes for UDP header
            return;
        }

        let ip_version: u8 = packet[0] >> 4;

        match ip_version {
            4 => {
                // IPv4
                let ip_header_length: usize = ((packet[0] & 0x0F) * 4).into();
                if packet.len() < ip_header_length {
                    return;
                }
                self.handle_ipv4_packet(&packet[0..ip_header_length], &packet[ip_header_length..]);
            }
            6 => {
                // No IPv6 support yet
                return;
            }
            _ => {
                // Unknown IP version
                return;
            }
        }

        // Check if it's a UDP or TCP packet
        // If it's UDP, check if it's DNS, RADIUS, SIP, etc.
        // If it's TCP, check if it's HTTP, TLS, etc.
        // Extract the relevant information and store it
    }
}
