//! Pure validators for the single resource advertised by this authorization server.
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};

pub(super) fn valid_resource(resource: &str) -> bool {
    if resource.is_empty() || resource.len() > 2048 || resource.trim() != resource {
        return false;
    }
    let Ok(url) = reqwest::Url::parse(resource) else { return false; };
    let loopback = url.host_str().is_some_and(|host| {
        host == "localhost" || host.trim_matches(['[', ']'])
            .parse::<std::net::IpAddr>().is_ok_and(|ip| ip.is_loopback())
    });
    (url.scheme() == "https" || (url.scheme() == "http" && loopback))
        && url.host_str().is_some() && url.username().is_empty()
        && url.password().is_none() && url.fragment().is_none() && url.query().is_none()
}

pub(super) fn valid_challenge(challenge: &str) -> bool {
    challenge.len() == 43 && URL_SAFE_NO_PAD.decode(challenge).ok().is_some_and(|bytes| {
        bytes.len() == 32 && URL_SAFE_NO_PAD.encode(bytes) == challenge
    })
}
