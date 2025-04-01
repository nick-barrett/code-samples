use crate::PacketDirection;

#[derive(Clone, Copy)]
struct TcpHostSeq {
    /// Most recent sequence number that the host was sent
    seq_no: u32,
    /// Expected next sequence number to send to the host
    next_seq_no: u32,
    /// Most recent acknowledgment number that the host sent
    ack_no: u32,
    /// Advertised window size of the host
    window_size: u16,
    /// Window scale option advertised by the host
    window_scale: u8,
}

#[derive(Clone, Copy)]
pub enum TcpState {
    /// Initial state before processing initial SYN
    Listen,
    /// State after seeing SYN from client to server
    SynSent {
        client_window_size: u16,
        /// Window scale option advertised by the client
        client_window_scale: u8,
        /// Most recent sequence number sent to the server
        server_seq_no: u32,
        /// Expected next sequence number to send to the server
        server_next_seq_no: u32,
    },
    /// State after seeing SYN-ACK from server
    SynReceived {
        /// Most recent sequence number sent to the server
        server_seq_no: u32,
        /// Expected next sequence number to send to the server
        server_next_seq_no: u32,
        /// Most recent acknowledgment number sent to the client
        server_ack_no: u32,
        /// Advertised window size of the server
        server_window_size: u16,
        /// Window scale option advertised by the server
        server_window_scale: u8,

        /// Most recent sequence number sent to the client
        client_seq_no: u32,
        /// Expected next sequence number to send to the client
        client_next_seq_no: u32,
        /// Advertised window size of the client
        client_window_size: u16,
        /// Window scale option advertised by the client
        client_window_scale: u8,
    },
    /// State after seeing ACK from client
    Established {
        client_seq: TcpHostSeq,
        server_seq: TcpHostSeq,
    },
    /// State after seeing FIN from client
    /// Waiting for ACK-FIN from server
    ClientFin,
    /// State after seeing FIN from server
    /// Waiting for ACK-FIN from client
    ServerFin,
    /// State after seeing ACK-FIN from server/client
    /// Waiting for last ACK from client/server and TCP FIN timeout
    Closing,
    /// State after TCP FIN timeout has expired
    Closed,
}

pub struct TcpHostStats {
    syn_count: u8,
    syn_rexmit_count: u8,

    rst_count: u8,
    rst_rexmit_count: u8,

    rexmit_count: u32,
    rexmit_bytes: usize,
}

impl TcpHostStats {
    fn new() -> Self {
        Self {
            syn_count: 0,
            syn_rexmit_count: 0,
            rst_count: 0,
            rst_rexmit_count: 0,
            rexmit_count: 0,
            rexmit_bytes: 0,
        }
    }
}

pub struct TcpSession {
    client_stats: TcpHostStats,
    server_stats: TcpHostStats,

    state: TcpState,
}

impl TcpSession {
    pub fn new() -> Self {
        Self {
            client_stats: TcpHostStats::new(),
            server_stats: TcpHostStats::new(),
            state: TcpState::Listen,
        }
    }

    fn process_listen(&mut self, tcp_input: &TcpPacketInput, options: &[TcpOption]) {
        if tcp_input.syn() {
            self.state = TcpState::SynSent {
                client_window_size: tcp_input.window,
                client_window_scale: 0,
                server_seq_no: tcp_input.seq_no,
                server_next_seq_no: tcp_input.seq_no + 1,
            };
        }

        if tcp_input.syn() {
            self.client_stats.syn_count += 1;
        }
        if tcp_input.rst() {
            self.client_stats.rst_count += 1;
        }
    }

    fn process_syn_sent(&mut self, tcp_input: &TcpPacketInput, options: &[TcpOption]) {
        let ack_no = tcp_input.ack_no();

        if ack_no.is_some() && tcp_input.syn() {
            // SYN-ACK packet from server
            self.state = TcpState::SynReceived {
                server_seq_no: tcp_input.seq_no,
                server_next_seq_no: tcp_input.seq_no + 1,
                server_ack_no: ack_no.unwrap(),
                server_window_size: tcp_input.window,
                server_window_scale: 0,

                client_seq_no: 0,
                client_next_seq_no: 0,
                client_window_size: 0,
                client_window_scale: 0,
            };
        }
    }

    fn process_syn_received(&mut self, tcp_input: &TcpPacketInput, options: &[TcpOption]) {
        let ack_no = tcp_input.ack_no();

        if ack_no.is_some() && tcp_input.syn() {
            // SYN-ACK packet from server
            self.state = TcpState::Established {
                client_seq: TcpHostSeq {
                    seq_no: tcp_input.seq_no,
                    next_seq_no: tcp_input.seq_no + 1,
                    ack_no: ack_no.unwrap(),
                    window_size: tcp_input.window,
                    window_scale: 0,
                },
                server_seq: TcpHostSeq {
                    seq_no: tcp_input.seq_no,
                    next_seq_no: tcp_input.seq_no + 1,
                    ack_no: ack_no.unwrap(),
                    window_size: tcp_input.window,
                    window_scale: 0,
                },
            };
        }
    }

    fn process_client_fin(&mut self, tcp_input: &TcpPacketInput) {}

    fn process_server_fin(&mut self, tcp_input: &TcpPacketInput) {}

    fn process_closing(&mut self, tcp_input: &TcpPacketInput) {}

    #[inline]
    fn process_established(&mut self, tcp_input: &TcpPacketInput, sack_ranges: &[TcpSackRange]) {}

    pub fn process_packet(&mut self, buffer: &[u8], direction: PacketDirection) {
        let mut sack_ranges = [TcpSackRange(0, 0); 4];
        let mut options = [TcpOption::NoOp; 4];

        let tcp_input =
            TcpPacketInput::from_buffer(direction, buffer, &mut sack_ranges, &mut options);

        let options_param = &options[..tcp_input.option_count as usize];
        let sack_ranges_param = &sack_ranges[..tcp_input.sack_range_count as usize];

        match self.state.clone() {
            TcpState::Listen => {
                self.process_listen(&tcp_input, options_param);
            }
            TcpState::SynSent { .. } => {
                self.process_syn_sent(&tcp_input, options_param);
            }
            TcpState::SynReceived { .. } => {
                self.process_syn_received(&tcp_input, options_param);
            }
            TcpState::Established { .. } => {
                self.process_established(&tcp_input, sack_ranges_param);
            }
            TcpState::ClientFin => {
                self.process_client_fin(&tcp_input);
            }
            TcpState::ServerFin => {
                self.process_server_fin(&tcp_input);
            }
            TcpState::Closing => {
                self.process_closing(&tcp_input);
            }
            TcpState::Closed => {
                // Session is closed, ignore any further packets
            }
            _ => {}
        };
    }
}

#[derive(Clone, Copy)]
struct TcpSackRange(u32, u32);

impl TcpSackRange {
    pub fn new(start: u32, end: u32) -> Self {
        TcpSackRange(start, end)
    }

    #[inline]
    pub fn start(&self) -> u32 {
        self.0
    }

    #[inline]
    pub fn end(&self) -> u32 {
        self.1
    }
}

#[derive(Clone, Copy)]
struct TcpTimestamp(u32, u32);

impl TcpTimestamp {
    pub fn new(timestamp: u32, echo: u32) -> Self {
        TcpTimestamp(timestamp, echo)
    }

    #[inline]
    pub fn timestamp(&self) -> u32 {
        self.0
    }

    #[inline]
    pub fn echo(&self) -> u32 {
        self.1
    }
}

/// TCP options that are infrequent.
/// These options should only appear in SYN packets.
#[derive(Clone, Copy)]
enum TcpOption {
    /// No operation option
    /// This is ONLY used to fill a static-length option array
    NoOp,
    /// Maximum segment size option
    /// SYN only
    MSS { mss: u16 },
    /// Window scale option
    /// SYN only
    WindowScale { scale: u8 },
    /// Selective acknowledgment supported option
    /// SYN only
    SackPermitted,
}

struct TcpPacketInput {
    direction: PacketDirection,
    seq_no: u32,
    ack_no: u32,
    window: u16,
    urgent: u16,
    flags: u8,
    sack_range_count: u8,
    timestamp: Option<TcpTimestamp>,
    option_count: u8,
    payload_offset: u8,
}

impl TcpPacketInput {
    fn from_buffer(
        direction: PacketDirection,
        buffer: &[u8],
        sack_ranges: &mut [TcpSackRange],
        options: &mut [TcpOption],
    ) -> Self {
        let seq_no = u32::from_be_bytes([buffer[4], buffer[5], buffer[6], buffer[7]]);
        let ack_no = u32::from_be_bytes([buffer[8], buffer[9], buffer[10], buffer[11]]);

        let data_offset = 4 * (buffer[12] >> 4);
        let flags = buffer[13];

        let window = u16::from_be_bytes([buffer[14], buffer[15]]);
        let urgent = u16::from_be_bytes([buffer[18], buffer[19]]);

        let mut timestamp: Option<TcpTimestamp> = None;
        let mut sack_count = 0 as u8;

        let options_data = &buffer[20..data_offset as usize];
        let mut option_count = 0 as u8;

        let mut options_data_index = 0;
        while options_data_index < options_data.len() && (option_count as usize) < options.len() {
            let option_type = options_data[options_data_index];
            match option_type {
                0 => {
                    // End of option list
                    break;
                }
                1 => {
                    // No operation - used for padding in the packet
                    options_data_index += 1;
                }
                2 => {
                    // Maximum segment size
                    if options_data_index + 3 < options_data.len() {
                        let mss = u16::from_be_bytes([
                            options_data[options_data_index + 2],
                            options_data[options_data_index + 3],
                        ]);
                        options[option_count as usize] = TcpOption::MSS { mss };
                        option_count += 1;
                        options_data_index += 4;
                    } else {
                        break;
                    }
                }
                3 => {
                    // Window scale
                    if options_data_index + 2 < options_data.len() {
                        let scale = options_data[options_data_index + 2];
                        options[option_count as usize] = TcpOption::WindowScale { scale };
                        option_count += 1;
                        options_data_index += 3;
                    } else {
                        break;
                    }
                }
                4 => {
                    // Selective acknowledgment permitted
                    options[option_count as usize] = TcpOption::SackPermitted;
                    option_count += 1;
                    options_data_index += 2;
                }
                5 => {
                    // Selective acknowledgment
                    if options_data_index + 1 < options_data.len() {
                        let length = options_data[options_data_index + 1];

                        if options_data_index + (length as usize) < options_data.len() {
                            options_data_index += 2;

                            let block_count = (length - 2) / 8;

                            if (block_count as usize) > sack_ranges.len() {
                                break;
                            }

                            sack_count = block_count;

                            for block_index in 0..block_count {
                                let sack_start = u32::from_be_bytes([
                                    options_data[options_data_index],
                                    options_data[options_data_index + 1],
                                    options_data[options_data_index + 2],
                                    options_data[options_data_index + 3],
                                ]);
                                let sack_end = u32::from_be_bytes([
                                    options_data[options_data_index + 4],
                                    options_data[options_data_index + 5],
                                    options_data[options_data_index + 6],
                                    options_data[options_data_index + 7],
                                ]);

                                sack_ranges[block_index as usize] =
                                    TcpSackRange::new(sack_start, sack_end);

                                options_data_index += 8;
                            }
                        } else {
                            break;
                        }
                    }
                }
                8 => {
                    // Timestamp
                    if options_data_index + 9 < options_data.len() {
                        let timestamp_value = u32::from_be_bytes([
                            options_data[options_data_index + 2],
                            options_data[options_data_index + 3],
                            options_data[options_data_index + 4],
                            options_data[options_data_index + 5],
                        ]);
                        let echo_value = u32::from_be_bytes([
                            options_data[options_data_index + 6],
                            options_data[options_data_index + 7],
                            options_data[options_data_index + 8],
                            options_data[options_data_index + 9],
                        ]);
                        timestamp = Some(TcpTimestamp::new(timestamp_value, echo_value));
                        options_data_index += 10;
                    } else {
                        break;
                    }
                }
                _ => {
                    // Unknown option, skip it
                    if options_data_index + 1 < options_data.len() {
                        let length = options_data[options_data_index + 1] as usize;
                        options_data_index += length;
                    } else {
                        break;
                    }
                }
            }
        }

        Self {
            direction,
            seq_no,
            ack_no,
            window,
            urgent,
            flags,
            sack_range_count: sack_count,
            timestamp,
            option_count,
            payload_offset: data_offset,
        }
    }

    #[inline]
    fn ack_no(&self) -> Option<u32> {
        self.ack().then_some(self.ack_no)
    }

    #[inline]
    fn urgent_ptr(&self) -> Option<u16> {
        self.urg().then_some(self.urgent)
    }

    #[inline]
    fn cwr(&self) -> bool {
        self.flags & 0x80 != 0
    }
    #[inline]
    fn ece(&self) -> bool {
        self.flags & 0x40 != 0
    }
    #[inline]
    fn urg(&self) -> bool {
        self.flags & 0x20 != 0
    }
    #[inline]
    fn ack(&self) -> bool {
        self.flags & 0x10 != 0
    }
    #[inline]
    fn psh(&self) -> bool {
        self.flags & 0x08 != 0
    }
    #[inline]
    fn rst(&self) -> bool {
        self.flags & 0x04 != 0
    }
    #[inline]
    fn syn(&self) -> bool {
        self.flags & 0x02 != 0
    }
    #[inline]
    fn fin(&self) -> bool {
        self.flags & 0x01 != 0
    }
}
