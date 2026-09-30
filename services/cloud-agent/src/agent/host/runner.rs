//! Multiplex controls with bounded native workers. All wire writes are sequenced.
use super::super::{wire::SnapshotChallenge, AgentConfig, AgentError};
use super::{
    authority::ProjectedHost,
    connection::{self, send_control, Incoming, Socket},
    error_result, now, LocalHost, Worker,
};
use crate::{
    channel::ControlMessage,
    execution::{
        ExecutionBinding, ExecutionReply, ExecutionRequest, PeerBinding, EXECUTION_VERSION,
    },
};
use std::{
    collections::{HashMap, VecDeque},
    sync::Arc,
    time::Duration,
};
use tokio::{task::JoinSet, time::Instant};
use uuid::Uuid;

const ACK_TIMEOUT: Duration = Duration::from_secs(10);
const MAX_PROJECTIONS: usize = 32;
struct PendingProjection {
    seq: i64,
    sent: Instant,
    value: ProjectedHost,
}
async fn projection<H: LocalHost>(
    socket: &mut Socket,
    cfg: &AgentConfig,
    worker: &Worker<H>,
    boot: Uuid,
    seq: &mut i64,
    next_send: &mut Instant,
) -> Result<ProjectedHost, AgentError> {
    let expected = send_control(socket, seq, next_send, |seq| {
        ControlMessage::ProjectionChallenge { seq }
    })
    .await?;
    let Incoming::ProjectionChallenge {
        seq: n,
        gateway_boot,
        nonce,
        expires_at,
        snapshot_valid_until,
    } = connection::receive(socket).await?
    else {
        return Err(AgentError::Protocol);
    };
    if n != expected {
        return Err(AgentError::Protocol);
    }
    let snapshot = worker.snapshot().await?;
    if snapshot.epoch < cfg.authority_epoch {
        return Err(AgentError::LocalAuthority);
    }
    let revision = worker.revision()?;
    let proof = worker.signer.host_projection(
        SnapshotChallenge {
            boot: gateway_boot,
            nonce,
            expires_at,
            ceiling: snapshot_valid_until,
        },
        boot,
        revision,
        now()?,
        &snapshot,
    )?;
    let expected = send_control(socket, seq, next_send, |seq| ControlMessage::Projection {
        seq,
        proof,
    })
    .await?;
    match connection::receive(socket).await? {
        Incoming::ProjectionAck { seq: n } if n == expected => Ok(ProjectedHost {
            snapshot,
            revision,
            until: snapshot_valid_until,
        }),
        _ => Err(AgentError::Protocol),
    }
}
pub(super) async fn session<H: LocalHost>(
    cfg: &AgentConfig,
    worker: Arc<Worker<H>>,
) -> Result<(), AgentError> {
    let (mut socket, boot) = connection::connect(cfg, &worker.signer).await?;
    let mut seq = 0;
    let mut next_send = Instant::now();
    let expected = send_control(&mut socket, &mut seq, &mut next_send, |seq| {
        ControlMessage::Heartbeat { seq }
    })
    .await?;
    match connection::receive(&mut socket).await? {
        Incoming::HeartbeatAck { seq: n } if n == expected => {}
        _ => return Err(AgentError::Protocol),
    }
    let expected = send_control(&mut socket, &mut seq, &mut next_send, |seq| {
        ControlMessage::ExecutionReady {
            seq,
            version: EXECUTION_VERSION,
        }
    })
    .await?;
    let peer = match connection::receive(&mut socket).await? {
        Incoming::ExecutionReadyAck { seq: n, peer } if n == expected => peer,
        _ => return Err(AgentError::Protocol),
    };
    validate_peer(cfg, boot, &peer)?;
    // Register peer cleanup before invoking the native hook, including timeout.
    let _native_connection = NativeConnection {
        host: worker.host.clone(),
        peer: peer.clone(),
    };
    tokio::time::timeout(
        Duration::from_secs(3),
        worker.host.connected(peer.clone(), 30),
    )
    .await
    .map_err(|_| AgentError::LocalAuthority)??;
    let expected = send_control(&mut socket, &mut seq, &mut next_send, |seq| {
        ControlMessage::ApprovalReady { seq, version: 1 }
    })
    .await?;
    match connection::receive(&mut socket).await? {
        Incoming::ApprovalReadyAck { seq: n, version: 1 } if n == expected => {}
        _ => return Err(AgentError::Protocol),
    }
    let initial = projection(&mut socket, cfg, &worker, boot, &mut seq, &mut next_send).await?;
    tokio::time::timeout(
        Duration::from_secs(3),
        worker.host.projection_applied(initial.snapshot.clone()),
    )
    .await
    .map_err(|_| AgentError::LocalAuthority)??;
    let mut cache = VecDeque::from([initial]);
    let mut tasks: JoinSet<(ExecutionRequest, serde_json::Value)> = JoinSet::new();
    let mut active = HashMap::<Uuid, ExecutionBinding>::new();
    let mut approval_tasks: JoinSet<(crate::approval::ApprovalRequest, serde_json::Value)> =
        JoinSet::new();
    let mut approval_active = HashMap::<Uuid, crate::approval::ApprovalBinding>::new();
    let mut approval_acks = HashMap::<i64, (Uuid, Instant)>::new();
    let mut reply_acks = HashMap::<i64, (Uuid, Instant)>::new();
    let mut hb: Option<(i64, Instant)> = None;
    let mut challenge: Option<(i64, Instant)> = None;
    let mut pending: Option<PendingProjection> = None;
    let mut heartbeat_at = Instant::now();
    let mut projection_at = Instant::now();
    let mut ticks = tokio::time::interval(Duration::from_millis(200));
    ticks.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut incoming_budget = (Instant::now(), 0u32);
    loop {
        tokio::select! {
            _=ticks.tick()=>{
                if hb.as_ref().is_some_and(|x|x.1.elapsed()>ACK_TIMEOUT)
                    || challenge.as_ref().is_some_and(|x|x.1.elapsed()>ACK_TIMEOUT)
                    || pending.as_ref().is_some_and(|x|x.sent.elapsed()>ACK_TIMEOUT)
                    || reply_acks.values().any(|x|x.1.elapsed()>ACK_TIMEOUT)
                    || approval_acks.values().any(|x|x.1.elapsed()>ACK_TIMEOUT) {
                    return Err(AgentError::Transport);
                }
                let at=now()?;
                cache.retain(|x|x.until>at);
                if heartbeat_at.elapsed()>=Duration::from_secs(8) && hb.is_none() {
                    let n=send_control(&mut socket,&mut seq,&mut next_send,|seq|ControlMessage::Heartbeat{seq}).await?;
                    hb=Some((n,Instant::now()));heartbeat_at=Instant::now();
                }
                if projection_at.elapsed()>=Duration::from_secs(4) && challenge.is_none() && pending.is_none() {
                    let n=send_control(&mut socket,&mut seq,&mut next_send,|seq|ControlMessage::ProjectionChallenge{seq}).await?;
                    challenge=Some((n,Instant::now()));projection_at=Instant::now();
                }
            },
            finished=tasks.join_next(),if !tasks.is_empty()=>{
                let Some(done)=finished else {return Err(AgentError::ExecutionUnknown);};
                let (request,result)=done.map_err(|_|AgentError::ExecutionUnknown)?;
                if request.binding.deadline<=now()? {active.remove(&request.binding.request_id);continue;}
                let id=request.binding.request_id;
                let reply=ExecutionReply{binding:request.binding,result};
                reply.validate_for(&reply.binding,now()?).map_err(|_|AgentError::Protocol)?;
                let n=send_control(&mut socket,&mut seq,&mut next_send,
                    |seq|ControlMessage::ExecutionReply{seq,reply:Box::new(reply)}).await?;
                reply_acks.insert(n,(id,Instant::now()));
            },
            done=approval_tasks.join_next(),if !approval_tasks.is_empty()=>{
                let (request,result)=done.ok_or(AgentError::LocalAuthority)?
                    .map_err(|_|AgentError::LocalAuthority)?;
                if request.binding.deadline<=now()? {
                    approval_active.remove(&request.binding.request_id);continue;
                }
                let id=request.binding.request_id;
                let reply=crate::approval::ApprovalReply{binding:request.binding,result};
                reply.validate_for(&reply.binding,now()?).map_err(|_|AgentError::Protocol)?;
                let n=send_control(&mut socket,&mut seq,&mut next_send,
                    |seq|ControlMessage::ApprovalReply{seq,reply:Box::new(reply)}).await?;
                approval_acks.insert(n,(id,Instant::now()));
            },
            incoming=connection::receive(&mut socket)=>{
                let incoming=incoming?;
                if incoming_budget.0.elapsed()>=Duration::from_secs(1) {incoming_budget=(Instant::now(),0);}
                incoming_budget.1+=1;
                if incoming_budget.1>64 {return Err(AgentError::Protocol);}
                match incoming {
                    Incoming::HeartbeatAck{seq:n} if hb.as_ref().map(|x|x.0)==Some(n)=>{
                        tokio::time::timeout(Duration::from_secs(3),worker.host.heartbeat(peer.clone(),30))
                            .await.map_err(|_|AgentError::LocalAuthority)??;
                        hb=None;
                    },
                    Incoming::ProjectionChallenge{seq:n,gateway_boot,nonce,expires_at,snapshot_valid_until}
                        if challenge.as_ref().map(|x|x.0)==Some(n)=>{
                        challenge=None;
                        let snapshot=worker.snapshot().await?;
                        if snapshot.epoch<cfg.authority_epoch {return Err(AgentError::LocalAuthority);}
                        let revision=worker.revision()?;
                        let proof=worker.signer.host_projection(
                            SnapshotChallenge{boot:gateway_boot,nonce,expires_at,ceiling:snapshot_valid_until},
                            boot,revision,now()?,&snapshot)?;
                        let n=send_control(&mut socket,&mut seq,&mut next_send,|seq|ControlMessage::Projection{seq,proof}).await?;
                        pending=Some(PendingProjection{seq:n,sent:Instant::now(),
                            value:ProjectedHost{snapshot,revision,until:snapshot_valid_until}});
                    },
                    Incoming::ProjectionAck{seq:n} if pending.as_ref().map(|x|x.seq)==Some(n)=>{
                        let projection=pending.take().ok_or(AgentError::Protocol)?.value;
                        tokio::time::timeout(Duration::from_secs(3),worker.host.projection_applied(projection.snapshot.clone()))
                            .await.map_err(|_|AgentError::LocalAuthority)??;
                        while cache.len()>=MAX_PROJECTIONS {cache.pop_front();}
                        cache.push_back(projection);
                    },
                    Incoming::ExecutionReplyAck{seq:n}=>{
                        let (id,_)=reply_acks.remove(&n).ok_or(AgentError::Protocol)?;
                        active.remove(&id);
                    },
                    Incoming::ApprovalReplyAck{seq:n}=>{
                        let (id,_)=approval_acks.remove(&n).ok_or(AgentError::Protocol)?;
                        approval_active.remove(&id);
                    },
                    Incoming::ApprovalRequest{request}=>{
                        request.validate_at(&peer,now()?).map_err(|_|AgentError::Protocol)?;
                        if let Some(prior)=approval_active.get(&request.binding.request_id) {
                            if prior!=&request.binding {return Err(AgentError::Protocol);}
                            continue;
                        }
                        if approval_active.len()>=crate::approval::APPROVAL_CAPACITY {
                            return Err(AgentError::Capacity);
                        }
                        approval_active.insert(request.binding.request_id,request.binding.clone());
                        let host=worker.host.clone();
                        approval_tasks.spawn(async move {
                            let value=tokio::time::timeout(Duration::from_secs(3),host.authorization(request.clone())).await;
                            let result=match value {
                                Ok(Ok(value))=>value,
                                _=>error_result(AgentError::LocalAuthority),
                            };
                            (request,result)
                        });
                    },
                    Incoming::ExecutionRequest{request}=>{
                        request.validate_at(&peer,now()?).map_err(|_|AgentError::Protocol)?;
                        if let Some(previous)=active.get(&request.binding.request_id) {
                            // A duplicate cannot race a rejection reply against the actual winner.
                            if previous!=&request.binding {return Err(AgentError::Protocol);}
                            continue;
                        }
                        // Bounded wire replies are separate from the four execution slots.
                        // Worker::execute_inner rejects surplus work immediately without
                        // queuing it or cancelling already-admitted winners.
                        if active.len()>=crate::execution::MAX_IN_FLIGHT {
                            return Err(AgentError::Capacity);
                        }
                        let Some(projected)=cache.iter().find(|x|x.revision==request.binding.grant_revision).cloned() else {
                            let reply=ExecutionReply{binding:request.binding,result:error_result(AgentError::LocalAuthority)};
                            let id=reply.binding.request_id;
                            active.insert(id,reply.binding.clone());
                            let n=send_control(&mut socket,&mut seq,&mut next_send,
                                |seq|ControlMessage::ExecutionReply{seq,reply:Box::new(reply)}).await?;
                            reply_acks.insert(n,(id,Instant::now()));
                            continue;
                        };
                        active.insert(request.binding.request_id,request.binding.clone());
                        tasks.spawn(worker.clone().execute(request,peer.clone(),projected));
                    },
                    _=>return Err(AgentError::Protocol),
                }
            }
        }
    }
}
fn validate_peer(cfg: &AgentConfig, boot: Uuid, peer: &PeerBinding) -> Result<(), AgentError> {
    peer.validate().map_err(|_| AgentError::Protocol)?;
    if peer.connector != cfg.connector
        || peer.device != cfg.device
        || peer.device_epoch != cfg.device_epoch
        || peer.gateway_boot != boot
    {
        return Err(AgentError::Authentication);
    }
    Ok(())
}

struct NativeConnection<H: LocalHost> {
    host: Arc<H>,
    peer: PeerBinding,
}
impl<H: LocalHost> Drop for NativeConnection<H> {
    fn drop(&mut self) {
        self.host.disconnected(&self.peer);
    }
}
