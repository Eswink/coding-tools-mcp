//! Authenticated fixture peer over real loopback TCP. Not a production Agent host.
use crate::{channel_support, common, projection_support};
use axum::{body::Body, http::{header, Request}, Router};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use coding_tools_cloud_gateway::{channel::*, mcp::{self, MODERN}, projection::*};
use futures_util::{SinkExt, StreamExt};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::time::Duration;
use tokio::{net::{TcpListener, TcpStream}, task::JoinHandle};
use tokio_tungstenite::{tungstenite::{client::IntoClientRequest, Message}, WebSocketStream};
use tower::ServiceExt;
use uuid::Uuid;
pub type Peer = WebSocketStream<TcpStream>;
pub struct Harness {
    pub h: projection_support::Harness,
    pub c: ChannelController,
    pub app: Router,
    pub token: String,
    addr: std::net::SocketAddr,
    task: JoinHandle<()>,
}
impl Drop for Harness { fn drop(&mut self) { self.task.abort(); } }
impl Harness {
    pub async fn start() -> Self {
        let (h,c)=channel_support::setup().await;
        let token=h.f.tokens(Uuid::from_u128(8)).await.access_token.expose().to_owned();
        let listener=TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr=listener.local_addr().unwrap();
        let app=mcp::routes(h.f.store.clone(),c.clone());
        let router=agent_channel_routes(c.clone()).merge(app.clone());
        let task=tokio::spawn(async move { axum::serve(listener,router).await.unwrap(); });
        Self {h,c,app,token,addr,task}
    }
    pub async fn connect(&self) -> Peer {
        let mut req=format!("ws://{}/coding-tools/agent",self.addr).into_client_request().unwrap();
        req.headers_mut().insert("host",common::identity().authority().parse().unwrap());
        req.headers_mut().insert("sec-websocket-protocol",SUBPROTOCOL.parse().unwrap());
        let (mut p,_)=tokio_tungstenite::client_async(req,TcpStream::connect(self.addr).await.unwrap()).await.unwrap();
        let challenge:ConnectChallenge=serde_json::from_value(read(&mut p).await["challenge"].clone()).unwrap();
        let proof=channel_support::sign(&channel_support::claims(&challenge,self.h.device.id,self.h.device.epoch),&self.h.key);
        write(&mut p,&serde_json::to_value(proof).unwrap()).await;
        assert_eq!(read(&mut p).await["type"],"connected");
        p
    }
    pub async fn project(&self,p:&mut Peer,seq:i64,revision:i64) {
        write(p,&json!({"type":"projection_challenge","seq":seq})).await;
        let ch=read(p).await;
        let at=projection_support::clock(&self.h.f).await;
        let claims=ProjectionClaims {version:1,issuer:common::identity().issuer(),resource:common::identity().resource(),connector:common::identity().connector(),device:self.h.device.id,device_epoch:self.h.device.epoch,gateway_boot:serde_json::from_value(ch["gateway_boot"].clone()).unwrap(),challenge:ch["nonce"].as_str().unwrap().into(),revision,authority_epoch:1,issued_at:at,valid_until:ch["snapshot_valid_until"].as_i64().unwrap(),phase:ProjectionPhase::Active,execution:ExecutionState::Online,grant:Some(self.h.lease.clone()),drained_grant:None};
        let (b,s)=self.h.signed(&claims);
        write(p,&json!({"type":"projection","seq":seq+1,"proof":{"payload":URL_SAFE_NO_PAD.encode(b),"signature":URL_SAFE_NO_PAD.encode(s)}})).await;
        assert_eq!(read(p).await["type"],"projection_ack");
    }
    pub fn call(&self,id:i64,conversation:&str) -> JoinHandle<Value> {
        let app=self.app.clone(); let token=self.token.clone(); let conv=conversation.to_owned();
        tokio::spawn(async move {call(app,&token,id,&conv).await})
    }
}
pub async fn call(app:Router,token:&str,id:i64,conversation:&str)->Value {
    let value=json!({"jsonrpc":"2.0","id":id,"method":"tools/call","params":{"name":"workspace_probe","arguments":{},"_meta":{"openai/session":conversation,"io.modelcontextprotocol/protocolVersion":MODERN,"io.modelcontextprotocol/clientCapabilities":{},"io.modelcontextprotocol/clientInfo":{"name":"bridge-fixture","version":"1"}}}});
    let r=Request::builder().method("POST").uri(common::identity().resource_path()).header("host",common::identity().authority()).header(header::AUTHORIZATION,format!("Bearer {token}")).header(header::CONTENT_TYPE,"application/json").header(header::ACCEPT,"application/json, text/event-stream").header("mcp-protocol-version",MODERN).header("mcp-method","tools/call").header("mcp-name","workspace_probe").body(Body::from(value.to_string())).unwrap();
    let r=app.oneshot(r).await.unwrap();
    assert_eq!(r.status(),200);
    let b=r.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice::<Value>(&b).unwrap()["result"]["structuredContent"].clone()
}
pub async fn write(p:&mut Peer,v:&Value) { tokio::time::timeout(Duration::from_secs(3),p.send(Message::Text(v.to_string().into()))).await.unwrap().unwrap(); }
pub async fn read(p:&mut Peer)->Value {
    let r=tokio::time::timeout(Duration::from_secs(5),p.next()).await.expect("bounded peer response").expect("peer connected").expect("valid frame");
    let Message::Text(t)=r else {panic!("EXECUTION_BRIDGE_MISSING: expected bound execution frame, got closed control-only peer")};
    serde_json::from_str(&t).unwrap()
}
pub async fn ready(p:&mut Peer,seq:i64)->Value {
    write(p,&json!({"type":"execution_ready","seq":seq,"version":1})).await;
    let ack=read(p).await;
    assert_eq!(ack["type"],"execution_ready_ack","EXECUTION_BRIDGE_MISSING: no production execution negotiation");
    ack
}
