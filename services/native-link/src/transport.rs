use crate::{canonical::digest_json,projection::{Prepared,Tracker},wire::{self,ApprovalReply,ClientFrame,ExecutionReply,ServerFrame},ApprovalCall,ClaimOutcome,DeviceConfig,DeviceKey,ExecutionCall,Journal,LinkError,NativeHost,Result,Session};
use futures_util::{stream::FuturesUnordered,FutureExt,SinkExt,StreamExt};
use serde::Serialize;
use serde_json::Value;
use std::{collections::BTreeMap,panic::AssertUnwindSafe,sync::{Arc,Mutex},time::{Duration,Instant}};
use tokio::{net::TcpStream,sync::{OwnedSemaphorePermit,Semaphore},task::JoinHandle};
use tokio_tungstenite::{connect_async_tls_with_config,Connector,MaybeTlsStream,WebSocketStream,tungstenite::{self,client::IntoClientRequest,protocol::{Message,WebSocketConfig}}};
use tokio_util::sync::CancellationToken;

type Socket=WebSocketStream<MaybeTlsStream<TcpStream>>;

pub struct NativeLink<H:NativeHost> {
    cfg:DeviceConfig,
    key:Arc<DeviceKey>,
    journal:Arc<Journal>,
    host:Arc<H>,
    connector:Connector,
    capacity:Arc<Semaphore>,
    quarantined:Arc<Mutex<Vec<OwnedSemaphorePermit>>>,
}
impl<H:NativeHost> NativeLink<H> {
    pub fn new(cfg:DeviceConfig,key:Arc<DeviceKey>,journal:Arc<Journal>,host:Arc<H>,trusted_ca_der:Option<Vec<u8>>)->Result<Self> {
        cfg.validate()?;journal.check_binding(&cfg,&key)?;
        let mut roots=rustls::RootCertStore::empty();
        if let Some(bytes)=trusted_ca_der {
            if bytes.is_empty()||bytes.len()>65536 {return Err(LinkError::Configuration);}
            roots.add(rustls::pki_types::CertificateDer::from(bytes)).map_err(|_|LinkError::Configuration)?;
        }else{roots.extend(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());}
        let tls=rustls::ClientConfig::builder_with_provider(Arc::new(rustls::crypto::ring::default_provider()))
            .with_safe_default_protocol_versions().map_err(|_|LinkError::Tls)?
            .with_root_certificates(roots).with_no_client_auth();
        Ok(Self{cfg,key,journal,host,connector:Connector::Rustls(Arc::new(tls)),
            capacity:Arc::new(Semaphore::new(4)),quarantined:Arc::new(Mutex::new(Vec::new()))})
    }
    pub fn requires_local_recovery(&self)->bool {
        self.quarantined.lock().map(|v|!v.is_empty()).unwrap_or(true)
    }
    /// Bounded exponential backoff with no saved execution queue. TLS/auth/protocol
    /// failures require local intervention, rather than retrying a weaker channel.
    pub async fn run(&self,stop:CancellationToken)->Result<()> {
        let mut attempts=0u32;
        loop {
            if stop.is_cancelled(){return Ok(());}
            let began=Instant::now();
            let result=tokio::select!{biased;_=stop.cancelled()=>return Ok(()),r=self.one_session()=>r};
            match result {
                Err(LinkError::Transport)=>{},
                other=>return other,
            }
            if began.elapsed()>=Duration::from_secs(30){attempts=0;}
            attempts=attempts.saturating_add(1);
            let mut noise=[0;2];
            use ring::rand::SecureRandom;
            ring::rand::SystemRandom::new().fill(&mut noise).map_err(|_|LinkError::Transport)?;
            let delay=(1u64<<attempts.saturating_sub(1).min(5)).min(30)*1000+u16::from_be_bytes(noise) as u64%501;
            tokio::select!{biased;_=stop.cancelled()=>return Ok(()),_=tokio::time::sleep(Duration::from_millis(delay))=>{}}
        }
    }
    async fn one_session(&self)->Result<()> {
        let mut request=self.cfg.endpoint()?.into_client_request().map_err(|_|LinkError::Configuration)?;
        request.headers_mut().insert("sec-websocket-protocol",wire::SUBPROTOCOL.parse().map_err(|_|LinkError::Configuration)?);
        let limits=WebSocketConfig::default().max_message_size(Some(wire::MAX_MESSAGE)).max_frame_size(Some(wire::MAX_MESSAGE))
            .write_buffer_size(0).max_write_buffer_size(wire::MAX_MESSAGE*2);
        let (mut socket,response)=tokio::time::timeout(Duration::from_secs(10),connect_async_tls_with_config(request,Some(limits),false,Some(self.connector.clone())))
            .await.map_err(|_|LinkError::Transport)?.map_err(classify)?;
        if response.headers().get_all("sec-websocket-protocol").iter().count()!=1
            || response.headers().get("sec-websocket-protocol").and_then(|h|h.to_str().ok())!=Some(wire::SUBPROTOCOL) {return Err(LinkError::Protocol);}
        let ServerFrame::ConnectChallenge{challenge}=receive(&mut socket).await? else{return Err(LinkError::Protocol);};
        let boot=challenge.gateway_boot;
        let proof=self.key.connect(&self.cfg,&challenge,crate::now()?)?;
        let mut sent=Instant::now()-Duration::from_millis(200);
        send(&mut socket,&proof,&mut sent).await?;
        match receive(&mut socket).await? {
            ServerFrame::Connected{heartbeat_seconds:10,lease_seconds:30}=>{},
            _=>return Err(LinkError::Protocol),
        }
        let mut seq=1;
        send(&mut socket,&ClientFrame::NativeReady{seq,version:1},&mut sent).await?;
        let peer=match receive(&mut socket).await? {
            ServerFrame::NativeReadyAck{seq:1,peer}=>peer,
            _=>return Err(LinkError::Protocol),
        };
        peer.validate()?;
        if peer.connector!=self.cfg.connector()||peer.device!=self.cfg.device()||peer.device_epoch!=self.cfg.device_epoch()||peer.gateway_boot!=boot {return Err(LinkError::Protocol);}
        let session=Session::established(self.cfg.issuer().to_owned(),peer,crate::now()?)?;
        struct Close(Session);
        impl Drop for Close{fn drop(&mut self){self.0.close();}}
        let _close=Close(session.clone());
        self.host.connected(&session)?;
        let mut tracker=Tracker::<H::Proof>::new(self.journal.clone())?;
        tracker.reconnect()?;
        let mut pending:BTreeMap<i64,(Instant,Ack<H::Proof>)>=BTreeMap::new();
        let mut jobs:FuturesUnordered<JoinHandle<Finished>>=FuturesUnordered::new();
        let mut ticks=tokio::time::interval(Duration::from_secs(2));
        ticks.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        let mut heartbeat_at=Instant::now()-Duration::from_secs(8);
        let mut inbound=(Instant::now(),0u32);
        loop {
            tokio::select! {
                _=ticks.tick()=> {
                    if !session.is_current(){return Err(LinkError::Transport);}
                    if pending.values().any(|(at,_)|at.elapsed()>Duration::from_secs(10)){return Err(LinkError::Transport);}
                    if pending.len()>32 {return Err(LinkError::Protocol);}
                    if heartbeat_at.elapsed()>=Duration::from_secs(8) && !pending.values().any(|(_,a)|matches!(a,Ack::Heartbeat(_))) {
                        let n=next(&mut seq)?;let at=crate::now()?;
                        send(&mut socket,&ClientFrame::Heartbeat{seq:n},&mut sent).await?;
                        pending.insert(n,(Instant::now(),Ack::Heartbeat(at)));heartbeat_at=Instant::now();
                    }
                    if !pending.values().any(|(_,a)|matches!(a,Ack::Challenge|Ack::Projection(_))) {
                        let n=next(&mut seq)?;
                        send(&mut socket,&ClientFrame::ProjectionChallenge{seq:n},&mut sent).await?;
                        pending.insert(n,(Instant::now(),Ack::Challenge));
                    }
                },
                job=jobs.next(),if !jobs.is_empty()=> {
                    let finished=job.ok_or(LinkError::Protocol)?.map_err(|_|LinkError::Protocol)?;
                    if !session.is_current(){return Err(LinkError::Transport);}
                    match finished {
                        Finished::Execution(reply)=> {
                            if reply.binding.deadline<=crate::now()? {continue;}
                            let n=next(&mut seq)?;
                            send(&mut socket,&ClientFrame::ExecutionReply{seq:n,reply},&mut sent).await?;
                            pending.insert(n,(Instant::now(),Ack::Execution));
                        },
                        Finished::Approval(reply)=> {
                            if reply.binding.deadline<=crate::now()? {continue;}
                            let n=next(&mut seq)?;
                            send(&mut socket,&ClientFrame::ApprovalReply{seq:n,reply},&mut sent).await?;
                            pending.insert(n,(Instant::now(),Ack::Approval));
                        },
                    }
                },
                incoming=socket.next()=> {
                    let frame=incoming.ok_or(LinkError::Transport)?.map_err(classify)?;
                    if inbound.0.elapsed()>=Duration::from_secs(1){inbound=(Instant::now(),0);}
                    inbound.1+=1;
                    if inbound.1>32{return Err(LinkError::Protocol);}
                    let text=match frame {
                        Message::Text(text)=>text,
                        Message::Ping(_)|Message::Pong(_)=>{socket.flush().await.map_err(classify)?;continue;},
                        Message::Close(_)=>return Err(LinkError::Transport),
                        _=>return Err(LinkError::Protocol),
                    };
                    match ServerFrame::parse(&text)? {
                        ServerFrame::HeartbeatAck{seq:n}=> {
                            let (_,Ack::Heartbeat(at))=pending.remove(&n).ok_or(LinkError::Protocol)? else{return Err(LinkError::Protocol);};
                            session.renew(at)?;
                        },
                        ServerFrame::ProjectionChallenge{seq:n,gateway_boot,nonce,expires_at,snapshot_valid_until}=> {
                            let (_,Ack::Challenge)=pending.remove(&n).ok_or(LinkError::Protocol)? else{return Err(LinkError::Protocol);};
                            let at=crate::now()?;
                            if gateway_boot!=boot||!wire::valid_digest(&nonce)||expires_at<=at||expires_at>at+60
                                ||snapshot_valid_until<=at||snapshot_valid_until>expires_at||snapshot_valid_until>at+30 {return Err(LinkError::Protocol);}
                            let observation=tokio::time::timeout(Duration::from_secs(2),self.host.observe(&session)).await.map_err(|_|LinkError::NotApproved)??;
                            let until=snapshot_valid_until.min(session.expires_at());
                            let prepared=tracker.prepare(observation,crate::now()?,until)?;
                            let proof=self.key.projection(&self.cfg,boot,&nonce,prepared.offered.revision,crate::now()?,until,&prepared.offered.state)?;
                            let n=next(&mut seq)?;
                            send(&mut socket,&ClientFrame::Projection{seq:n,proof},&mut sent).await?;
                            pending.insert(n,(Instant::now(),Ack::Projection(prepared)));
                        },
                        ServerFrame::ProjectionAck{seq:n}=> {
                            let (_,Ack::Projection(prepared))=pending.remove(&n).ok_or(LinkError::Protocol)? else{return Err(LinkError::Protocol);};
                            tracker.acknowledged(prepared)?;
                        },
                        ServerFrame::ExecutionReplyAck{seq:n}=> {
                            if !matches!(pending.remove(&n),Some((_,Ack::Execution))){return Err(LinkError::Protocol);}
                        },
                        ServerFrame::ApprovalReplyAck{seq:n}=> {
                            if !matches!(pending.remove(&n),Some((_,Ack::Approval))){return Err(LinkError::Protocol);}
                        },
                        ServerFrame::ExecutionRequest{request}=> {
                            request.validate_at(session.peer(),crate::now()?)?;
                            let result=tracker.proof_for(&request,&session,crate::now()?);
                            let capacity=self.capacity.clone().try_acquire_owned();
                            if result.is_err()||capacity.is_err()||jobs.len()>=4||self.requires_local_recovery() {
                                let code=if result.is_err(){"LOCAL_AUTHORITY_CHANGED"}else{"LOCAL_CAPACITY_EXHAUSTED"};
                                let reply=ExecutionReply{binding:request.binding,result:crate::tool_error(code)};
                                let n=next(&mut seq)?;
                                send(&mut socket,&ClientFrame::ExecutionReply{seq:n,reply},&mut sent).await?;
                                pending.insert(n,(Instant::now(),Ack::Execution));continue;
                            }
                            let proof=result?;let permit=capacity.map_err(|_|LinkError::Capacity)?;
                            let host=self.host.clone();let journal=self.journal.clone();let live=session.clone();let quarantine=self.quarantined.clone();
                            jobs.push(tokio::spawn(async move {
                                let mut permit=Some(permit);
                                let claim={let j=journal.clone();let r=request.clone();tokio::task::spawn_blocking(move||j.claim(&r)).await};
                                let result=match claim {
                                    Ok(Ok(ClaimOutcome::Fresh))=> {
                                        let call=ExecutionCall{session:live,request:request.clone(),proof};
                                        match AssertUnwindSafe(host.execute(call)).catch_unwind().await {
                                            Ok(result)=> {
                                                let result=bounded_result(result);
                                                let done={let j=journal.clone();let r=request.clone();let value=result.clone();tokio::task::spawn_blocking(move||j.complete(&r,&value)).await};
                                                if matches!(done,Ok(Ok(()))) {result}else {
                                                    quarantine_permit(&quarantine,&mut permit);
                                                    uncertain("LOCAL_RESULT_NOT_DURABLE")
                                                }
                                            },
                                            Err(_)=>{quarantine_permit(&quarantine,&mut permit);uncertain("LOCAL_WORKER_OUTCOME_UNKNOWN")},
                                        }
                                    },
                                    Ok(Ok(ClaimOutcome::AlreadyClaimed{..}))=>uncertain("REQUEST_ALREADY_CLAIMED"),
                                    Ok(Err(LinkError::ReplayConflict))=>crate::tool_error("REQUEST_ID_CONFLICT"),
                                    _=>crate::tool_error("LOCAL_JOURNAL_REJECTED"),
                                };
                                Finished::Execution(ExecutionReply{binding:request.binding,result})
                            }));
                        },
                        ServerFrame::ApprovalRequest{request}=> {
                            request.validate_at(session.peer(),crate::now()?)?;
                            let permit=self.capacity.clone().try_acquire_owned();
                            if permit.is_err()||jobs.len()>=4||!session.is_current() {
                                let reply=ApprovalReply{binding:request.binding,result:crate::tool_error("LOCAL_CAPACITY_EXHAUSTED")};
                                let n=next(&mut seq)?;
                                send(&mut socket,&ClientFrame::ApprovalReply{seq:n,reply},&mut sent).await?;
                                pending.insert(n,(Instant::now(),Ack::Approval));continue;
                            }
                            let permit=permit.map_err(|_|LinkError::Capacity)?;let host=self.host.clone();let live=session.clone();
                            jobs.push(tokio::spawn(async move {
                                let _permit=permit;let binding=request.binding.clone();
                                let result=AssertUnwindSafe(host.approval(ApprovalCall{session:live,request})).catch_unwind().await;
                                Finished::Approval(ApprovalReply{binding,result:bounded_result(result.unwrap_or(Err(LinkError::NotApproved)))})
                            }));
                        },
                        _=>return Err(LinkError::Protocol),
                    }
                },
            }
        }
    }
}
fn quarantine_permit(quarantine:&Mutex<Vec<OwnedSemaphorePermit>>,permit:&mut Option<OwnedSemaphorePermit>) {
    if let Some(permit)=permit.take() {
        if let Ok(mut q)=quarantine.lock(){q.push(permit);}else{std::mem::forget(permit);}
    }
}
fn bounded_result(result:Result<Value>)->Value {
    let value=result.unwrap_or_else(|_|crate::tool_error("LOCAL_EXECUTION_REJECTED"));
    if !value.is_object()||value.get("ok").and_then(Value::as_bool).is_none()||digest_json(&value,wire::MAX_RESULT).is_err() {
        let mut result=crate::tool_error("LOCAL_RESULT_UNAVAILABLE");
        result["execution_outcome"]=serde_json::json!("completed_without_output");result
    }else{value}
}
fn uncertain(code:&'static str)->Value {
    let mut value=crate::tool_error(code);value["execution_outcome"]=serde_json::json!("unknown");
    value["process_may_be_running"]=serde_json::json!(true);value
}
enum Finished{Execution(ExecutionReply),Approval(ApprovalReply)}
enum Ack<P>{Heartbeat(i64),Challenge,Projection(Prepared<P>),Execution,Approval}
fn next(seq:&mut i64)->Result<i64>{*seq=seq.checked_add(1).ok_or(LinkError::Protocol)?;Ok(*seq)}
async fn send(socket:&mut Socket,value:&impl Serialize,last:&mut Instant)->Result<()> {
    let raw=serde_json::to_string(value).map_err(|_|LinkError::Protocol)?;
    if raw.len()>wire::MAX_MESSAGE{return Err(LinkError::Protocol);}
    if let Some(delay)=Duration::from_millis(200).checked_sub(last.elapsed()){tokio::time::sleep(delay).await;}
    tokio::time::timeout(Duration::from_secs(2),socket.send(Message::Text(raw.into())))
        .await.map_err(|_|LinkError::Transport)?.map_err(classify)?;*last=Instant::now();Ok(())
}
async fn receive(socket:&mut Socket)->Result<ServerFrame> {
    tokio::time::timeout(Duration::from_secs(10),async {
        for _ in 0..16 {
            match socket.next().await.ok_or(LinkError::Transport)?.map_err(classify)? {
                Message::Text(raw)=>return ServerFrame::parse(&raw),
                Message::Ping(_)|Message::Pong(_)=>socket.flush().await.map_err(classify)?,
                Message::Close(_)=>return Err(LinkError::Transport),
                _=>return Err(LinkError::Protocol),
            }
        }
        Err(LinkError::Protocol)
    }).await.map_err(|_|LinkError::Transport)?
}
fn classify(error:tungstenite::Error)->LinkError {
    match error {
        tungstenite::Error::Io(ref e) if matches!(e.kind(),std::io::ErrorKind::InvalidData|std::io::ErrorKind::InvalidInput)=>LinkError::Tls,
        tungstenite::Error::Io(_)|tungstenite::Error::ConnectionClosed|tungstenite::Error::AlreadyClosed=>LinkError::Transport,
        tungstenite::Error::Tls(_)=>LinkError::Tls,
        tungstenite::Error::Http(r) if [429,502,503,504].contains(&r.status().as_u16())=>LinkError::Transport,
        tungstenite::Error::Http(_)=>LinkError::Credentials,
        _=>LinkError::Protocol,
    }
}
