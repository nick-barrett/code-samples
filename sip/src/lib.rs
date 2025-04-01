/*

Unicast UDP NAT Requirements - https://datatracker.ietf.org/doc/html/rfc4787

URI - https://datatracker.ietf.org/doc/html/rfc2396
URLs for telephone calls - https://datatracker.ietf.org/doc/html/rfc2806

SIP: Session Initiation Protocol - https://datatracker.ietf.org/doc/html/rfc3261
    SIP: Locating SIP Servers - https://datatracker.ietf.org/doc/html/rfc3263
    SIP: UA Capabilities - https://datatracker.ietf.org/doc/html/rfc3840
    Client-initiated connections with SIP - https://datatracker.ietf.org/doc/html/rfc5626
    ICE with SIP - https://datatracker.ietf.org/doc/html/rfc5768
    SIP: Locating SIP Servers (Dual-stack) - https://datatracker.ietf.org/doc/html/rfc7984

RTP / RTCP - https://datatracker.ietf.org/doc/html/rfc3550
    Symmetric RTP / RTCP - https://datatracker.ietf.org/doc/html/rfc4961
    RTP Header Extensions - https://datatracker.ietf.org/doc/html/rfc5285
        RTP SDES - https://datatracker.ietf.org/doc/html/rfc7941

SDP: Session Description Protocol - https://datatracker.ietf.org/doc/html/rfc8866
    SDP Offer/Answer Model - https://datatracker.ietf.org/doc/html/rfc3264
    SDP Media Bundling - https://datatracker.ietf.org/doc/html/rfc9143

STUN - https://datatracker.ietf.org/doc/html/rfc8489
    TURN - https://datatracker.ietf.org/doc/html/rfc8656

*/

pub struct SipUri {
    pub user: Option<String>,
    pub password: Option<String>,
    pub host: String,
    pub port: Option<u16>,
    pub params: Vec<(String, String)>,
    pub headers: Vec<(String, String)>,
}

pub enum Uri {
    Sip(SipUri),
    Sips(SipUri),
    Other {
        schema: String,
        schema_specific_part: String,
    },
}

pub struct Msg {
    pub start_line: StartLine,
    pub headers: Vec<Header>,
    pub body: Option<String>,
}

pub enum StartLine {
    Request(Request),
    Response(Status),
}

pub enum Method {
    Register,
    Invite,
    Ack,
    Cancel,
    Bye,
    Options,
    Other(String),
}

impl Method {
    pub fn from_str(s: &str) -> Self {
        match s {
            "REGISTER" => Method::Register,
            "INVITE" => Method::Invite,
            "ACK" => Method::Ack,
            "CANCEL" => Method::Cancel,
            "BYE" => Method::Bye,
            "OPTIONS" => Method::Options,
            _ => Method::Other(s.to_string()),
        }
    }

    pub fn to_str(&self) -> &str {
        match self {
            Method::Register => "REGISTER",
            Method::Invite => "INVITE",
            Method::Ack => "ACK",
            Method::Cancel => "CANCEL",
            Method::Bye => "BYE",
            Method::Options => "OPTIONS",
            Method::Other(s) => s.as_str(),
        }
    }
}

pub enum StatusCode {
    Trying,
    Ringing,
    CallBeingForwarded,
    Queued,
    SessionProgress,
    Ok,
    MultipleChoices,
    MovedPermanently,
    MovedTemporarily,
    UseProxy,
    AlternativeService,
    BadRequest,
    Unauthorized,
    PaymentRequired,
    Forbidden,
    NotFound,
    MethodNotAllowed,
    NotAcceptable406,
    ProxyAuthenticationRequired,
    RequestTimeout,
    Gone,
    RequestEntityTooLarge,
    RequestUriTooLong,
    UnsupportedMediaType,
    UnsupportedUriScheme,
    BadExtension,
    ExtensionRequired,
    IntervalTooBrief,
    TemporarilyUnavailable,
    CallOrTransactionDoesNotExist,
    LoopDetected,
    TooManyHops,
    AddressIncomplete,
    Ambiguous,
    BusyHere,
    RequestTerminated,
    NotAcceptableHere,
    RequestPending,
    Undecipherable,
    ServerInternalError,
    NotImplemented,
    BadGateway,
    ServiceUnavailable,
    ServerTimeout,
    VersionNotSupported,
    MessageTooLarge,
    BusyEverywhere,
    Decline,
    DoesNotExistAnywhere,
    NotAcceptable606,
}

impl StatusCode {
    pub fn from_code(code: u16) -> Option<StatusCode> {
        match code {
            100 => Some(StatusCode::Trying),
            180 => Some(StatusCode::Ringing),
            181 => Some(StatusCode::CallBeingForwarded),
            182 => Some(StatusCode::Queued),
            183 => Some(StatusCode::SessionProgress),
            200 => Some(StatusCode::Ok),
            300 => Some(StatusCode::MultipleChoices),
            301 => Some(StatusCode::MovedPermanently),
            302 => Some(StatusCode::MovedTemporarily),
            305 => Some(StatusCode::UseProxy),
            380 => Some(StatusCode::AlternativeService),
            400 => Some(StatusCode::BadRequest),
            401 => Some(StatusCode::Unauthorized),
            402 => Some(StatusCode::PaymentRequired),
            403 => Some(StatusCode::Forbidden),
            404 => Some(StatusCode::NotFound),
            405 => Some(StatusCode::MethodNotAllowed),
            406 => Some(StatusCode::NotAcceptable406),
            407 => Some(StatusCode::ProxyAuthenticationRequired),
            408 => Some(StatusCode::RequestTimeout),
            410 => Some(StatusCode::Gone),
            413 => Some(StatusCode::RequestEntityTooLarge),
            414 => Some(StatusCode::RequestUriTooLong),
            415 => Some(StatusCode::UnsupportedMediaType),
            416 => Some(StatusCode::UnsupportedUriScheme),
            420 => Some(StatusCode::BadExtension),
            421 => Some(StatusCode::ExtensionRequired),
            423 => Some(StatusCode::IntervalTooBrief),
            480 => Some(StatusCode::TemporarilyUnavailable),
            481 => Some(StatusCode::CallOrTransactionDoesNotExist),
            482 => Some(StatusCode::LoopDetected),
            483 => Some(StatusCode::TooManyHops),
            484 => Some(StatusCode::AddressIncomplete),
            485 => Some(StatusCode::Ambiguous),
            486 => Some(StatusCode::BusyHere),
            487 => Some(StatusCode::RequestTerminated),
            488 => Some(StatusCode::NotAcceptableHere),
            491 => Some(StatusCode::RequestPending),
            493 => Some(StatusCode::Undecipherable),
            500 => Some(StatusCode::ServerInternalError),
            501 => Some(StatusCode::NotImplemented),
            502 => Some(StatusCode::BadGateway),
            503 => Some(StatusCode::ServiceUnavailable),
            504 => Some(StatusCode::ServerTimeout),
            505 => Some(StatusCode::VersionNotSupported),
            513 => Some(StatusCode::MessageTooLarge),
            600 => Some(StatusCode::BusyEverywhere),
            603 => Some(StatusCode::Decline),
            604 => Some(StatusCode::DoesNotExistAnywhere),
            606 => Some(StatusCode::NotAcceptable606),
            _ => None,
        }
    }

    pub fn to_code(&self) -> u16 {
        match self {
            StatusCode::Trying => 100,
            StatusCode::Ringing => 180,
            StatusCode::CallBeingForwarded => 181,
            StatusCode::Queued => 182,
            StatusCode::SessionProgress => 183,
            StatusCode::Ok => 200,
            StatusCode::MultipleChoices => 300,
            StatusCode::MovedPermanently => 301,
            StatusCode::MovedTemporarily => 302,
            StatusCode::UseProxy => 305,
            StatusCode::AlternativeService => 380,
            StatusCode::BadRequest => 400,
            StatusCode::Unauthorized => 401,
            StatusCode::PaymentRequired => 402,
            StatusCode::Forbidden => 403,
            StatusCode::NotFound => 404,
            StatusCode::MethodNotAllowed => 405,
            StatusCode::NotAcceptable406 => 406,
            StatusCode::ProxyAuthenticationRequired => 407,
            StatusCode::RequestTimeout => 408,
            StatusCode::Gone => 410,
            StatusCode::RequestEntityTooLarge => 413,
            StatusCode::RequestUriTooLong => 414,
            StatusCode::UnsupportedMediaType => 415,
            StatusCode::UnsupportedUriScheme => 416,
            StatusCode::BadExtension => 420,
            StatusCode::ExtensionRequired => 421,
            StatusCode::IntervalTooBrief => 423,
            StatusCode::TemporarilyUnavailable => 480,
            StatusCode::CallOrTransactionDoesNotExist => 481,
            StatusCode::LoopDetected => 482,
            StatusCode::TooManyHops => 483,
            StatusCode::AddressIncomplete => 484,
            StatusCode::Ambiguous => 485,
            StatusCode::BusyHere => 486,
            StatusCode::RequestTerminated => 487,
            StatusCode::NotAcceptableHere => 488,
            StatusCode::RequestPending => 491,
            StatusCode::Undecipherable => 493,
            StatusCode::ServerInternalError => 500,
            StatusCode::NotImplemented => 501,
            StatusCode::BadGateway => 502,
            StatusCode::ServiceUnavailable => 503,
            StatusCode::ServerTimeout => 504,
            StatusCode::VersionNotSupported => 505,
            StatusCode::MessageTooLarge => 513,
            StatusCode::BusyEverywhere => 600,
            StatusCode::Decline => 603,
            StatusCode::DoesNotExistAnywhere => 604,
            StatusCode::NotAcceptable606 => 606,
        }
    }

    pub fn to_reason_phrase(&self) -> &'static str {
        match self {
            StatusCode::Trying => "Trying",
            StatusCode::Ringing => "Ringing",
            StatusCode::CallBeingForwarded => "Call Is Being Forwarded",
            StatusCode::Queued => "Queued",
            StatusCode::SessionProgress => "Session Progress",
            StatusCode::Ok => "OK",
            StatusCode::MultipleChoices => "Multiple Choices",
            StatusCode::MovedPermanently => "Moved Permanently",
            StatusCode::MovedTemporarily => "Moved Temporarily",
            StatusCode::UseProxy => "Use Proxy",
            StatusCode::AlternativeService => "Alternative Service",
            StatusCode::BadRequest => "Bad Request",
            StatusCode::Unauthorized => "Unauthorized",
            StatusCode::PaymentRequired => "Payment Required",
            StatusCode::Forbidden => "Forbidden",
            StatusCode::NotFound => "Not Found",
            StatusCode::MethodNotAllowed => "Method Not Allowed",
            StatusCode::NotAcceptable406 => "Not Acceptable",
            StatusCode::ProxyAuthenticationRequired => "Proxy Authentication Required",
            StatusCode::RequestTimeout => "Request Timeout",
            StatusCode::Gone => "Gone",
            StatusCode::RequestEntityTooLarge => "Request Entity Too Large",
            StatusCode::RequestUriTooLong => "Request-URI Too Long",
            StatusCode::UnsupportedMediaType => "Unsupported Media Type",
            StatusCode::UnsupportedUriScheme => "Unsupported URI Scheme",
            StatusCode::BadExtension => "Bad Extension",
            StatusCode::ExtensionRequired => "Extension Required",
            StatusCode::IntervalTooBrief => "Interval Too Brief",
            StatusCode::TemporarilyUnavailable => "Temporarily Unavailable",
            StatusCode::CallOrTransactionDoesNotExist => "Call/Transaction Does Not Exist",
            StatusCode::LoopDetected => "Loop Detected",
            StatusCode::TooManyHops => "Too Many Hops",
            StatusCode::AddressIncomplete => "Address Incomplete",
            StatusCode::Ambiguous => "Ambiguous",
            StatusCode::BusyHere => "Busy Here",
            StatusCode::RequestTerminated => "Request Terminated",
            StatusCode::NotAcceptableHere => "Not Acceptable Here",
            StatusCode::RequestPending => "Request Pending",
            StatusCode::Undecipherable => "Undecipherable",
            StatusCode::ServerInternalError => "Server Internal Error",
            StatusCode::NotImplemented => "Not Implemented",
            StatusCode::BadGateway => "Bad Gateway",
            StatusCode::ServiceUnavailable => "Service Unavailable",
            StatusCode::ServerTimeout => "Server Time-out",
            StatusCode::VersionNotSupported => "Version Not Supported",
            StatusCode::MessageTooLarge => "Message Too Large",
            StatusCode::BusyEverywhere => "Busy Everywhere",
            StatusCode::Decline => "Decline",
            StatusCode::DoesNotExistAnywhere => "Does Not Exist Anywhere",
            StatusCode::NotAcceptable606 => "Not Acceptable",
        }
    }
}

pub enum Version {
    V1,
    V2,
    Other(String),
}

pub struct Request {
    pub method: Method,
    pub uri: Uri,
    pub version: Version,
}

pub struct Status {
    pub version: Version,
    pub status: StatusCode,
}

pub struct Header {
    pub name: String,
    pub value: String,
}
