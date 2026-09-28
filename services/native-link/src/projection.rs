//! Locally-derived projection and exact request/proof correlation.
use crate::{journal::Offered,wire::{ExecutionRequest,ExecutionState,Phase,Projected},Journal,LinkError,LocalPhase,Observation,Result,Session};
use std::{collections::BTreeMap,sync::Arc};

struct Cached<P> { offered:Offered, proof:P, valid_until:i64 }
pub(crate) struct Prepared<P> { pub offered:Offered, pub proof:Option<P>, pub valid_until:i64 }
pub(crate) struct Tracker<P> {
    journal:Arc<Journal>,
    confirmed:Option<Offered>,
    retry:Option<Offered>,
    cache:BTreeMap<i64,Cached<P>>,
}
impl<P:Clone> Tracker<P> {
    pub(crate) fn new(journal:Arc<Journal>)->Result<Self> {
        let (confirmed,retry)=journal.projection_state()?;
        Ok(Self{journal,confirmed,retry,cache:BTreeMap::new()})
    }
    pub(crate) fn prepare(&mut self,observation:Observation<P>,at:i64,valid_until:i64)->Result<Prepared<P>> {
        validate_observation(&observation,at)?;
        let state=if let Some(retry)=&self.retry {
            // An ACK may have been lost. Reoffer the same ownership transition;
            // never skip directly from an unacknowledged drain to free.
            if matches!(retry.state.phase,Phase::Active|Phase::Pending)
                && !same_native(&observation,retry,at) {
                draining(&retry.state)
            } else {retry.state.clone()}
        } else {self.next_state(&observation,at)?};
        let proof=if state.phase==Phase::Active && state.execution==ExecutionState::Online {
            let grant=state.grant.as_ref().ok_or(LinkError::Protocol)?;
            if observation.grant.as_ref()!=Some(grant) || observation.phase!=LocalPhase::Active
                || !observation.execution_enabled || !observation.recovery_ready
                || observation.proof.is_none() || grant.expires_at<=at {return Err(LinkError::NotApproved);}
            observation.proof.clone()
        } else {None};
        let offer=self.journal.offer(Offered{revision:0,state,native_epoch:observation.native_epoch,
            native_revision:observation.native_revision,execution_generation:observation.execution_generation})?;
        self.retry=Some(offer.clone());
        Ok(Prepared{offered:offer,proof,valid_until})
    }
    fn next_state(&self,observation:&Observation<P>,at:i64)->Result<Projected> {
        let Some(old)=&self.confirmed else {
            return Ok(Projected{phase:if observation.recovery_ready&&observation.drain_safe {Phase::Free}else{Phase::RecoveryRequired},
                execution:ExecutionState::Offline,authority_epoch:1,grant:None,drained_grant:None});
        };
        let state=&old.state;
        if state.phase==Phase::Free || (state.phase==Phase::RecoveryRequired && state.grant.is_none()) {
            if state.phase!=Phase::Free {
                return Ok(if observation.recovery_ready&&observation.drain_safe {
                    Projected{phase:Phase::Free,execution:ExecutionState::Offline,authority_epoch:state.authority_epoch,grant:None,drained_grant:None}
                } else {state.clone()});
            }
            if matches!(observation.phase,LocalPhase::Pending|LocalPhase::Active) && observation.recovery_ready {
                let grant=observation.grant.clone().ok_or(LinkError::Protocol)?;
                if grant.expires_at<=at {return Ok(state.clone());}
                let phase=if observation.phase==LocalPhase::Pending {Phase::Pending}else{Phase::Active};
                let execution=if phase==Phase::Active && observation.execution_enabled {ExecutionState::Online}else{ExecutionState::Offline};
                return Ok(Projected{phase,execution,authority_epoch:self.journal.next_epoch()?,grant:Some(grant),drained_grant:None});
            }
            return Ok(state.clone());
        }
        let previous=state.grant.as_ref().ok_or(LinkError::Protocol)?;
        let same=observation.native_epoch==old.native_epoch
            && observation.grant.as_ref().is_some_and(|g|g.id==previous.id&&g.conversation==previous.conversation)
            && observation.recovery_ready;
        if state.phase==Phase::Pending && same && observation.phase==LocalPhase::Active {
            let grant=observation.grant.as_ref().ok_or(LinkError::Protocol)?;
            if grant.scopes.iter().all(|s|previous.scopes.contains(s)) && grant.issued_at==previous.issued_at && grant.expires_at>at {
                return Ok(Projected{phase:Phase::Active,execution:if observation.execution_enabled {ExecutionState::Online}else{ExecutionState::Offline},
                    authority_epoch:state.authority_epoch,grant:Some(grant.clone()),drained_grant:None});
            }
        }
        if same && ((state.phase==Phase::Active && observation.phase==LocalPhase::Active)
            || (state.phase==Phase::Pending && observation.phase==LocalPhase::Pending))
            && observation.grant.as_ref()==Some(previous) && previous.expires_at>at {
            let mut value=state.clone();
            value.execution=if value.phase==Phase::Active&&observation.execution_enabled {ExecutionState::Online}else{ExecutionState::Offline};
            return Ok(value);
        }
        if state.phase==Phase::Draining && observation.recovery_ready && observation.drain_safe {
            return Ok(Projected{phase:Phase::Free,execution:ExecutionState::Offline,authority_epoch:state.authority_epoch,
                grant:None,drained_grant:Some(previous.id)});
        }
        Ok(draining(state))
    }
    pub(crate) fn acknowledged(&mut self,prepared:Prepared<P>)->Result<()> {
        self.journal.acknowledge(prepared.offered.revision)?;
        self.confirmed=Some(prepared.offered.clone());self.retry=None;
        if let Some(proof)=prepared.proof {
            self.cache.insert(prepared.offered.revision,Cached{offered:prepared.offered,proof,valid_until:prepared.valid_until});
            while self.cache.len()>32 {self.cache.pop_first();}
        }
        Ok(())
    }
    pub(crate) fn proof_for(&mut self,request:&ExecutionRequest,session:&Session,at:i64)->Result<P> {
        request.validate_at(session.peer(),at)?;
        if !session.is_current() {return Err(LinkError::NotApproved);}
        self.cache.retain(|_,c|c.valid_until>at);
        let cached=self.cache.get(&request.binding.grant_revision).ok_or(LinkError::NotApproved)?;
        let state=&cached.offered.state;
        let grant=state.grant.as_ref().ok_or(LinkError::NotApproved)?;
        if state.phase!=Phase::Active || state.execution!=ExecutionState::Online
            || state.authority_epoch!=request.binding.authority_epoch
            || grant.id!=request.binding.grant_id || grant.conversation!=request.binding.conversation
            || !grant.scopes.contains(&request.binding.scope) || grant.expires_at<=at
            || request.binding.deadline>grant.expires_at {return Err(LinkError::NotApproved);}
        Ok(cached.proof.clone())
    }
    pub(crate) fn reconnect(&mut self)->Result<()> {
        let (confirmed,retry)=self.journal.projection_state()?;
        self.confirmed=confirmed;self.retry=retry;self.cache.clear();Ok(())
    }
}
fn validate_observation<P>(o:&Observation<P>,at:i64)->Result<()> {
    if o.native_epoch==0 || o.native_revision==0 || o.execution_generation==0
        || o.grant.as_ref().is_some_and(|g|!g.valid())
        || (matches!(o.phase,LocalPhase::Pending|LocalPhase::Active) && o.grant.is_none())
        || (o.phase==LocalPhase::Free && o.grant.is_some())
        || (o.phase==LocalPhase::Active && o.execution_enabled
            && (o.proof.is_none()||!o.recovery_ready||o.grant.as_ref().is_none_or(|g|g.expires_at<=at))) {
        return Err(LinkError::NotApproved);
    }
    Ok(())
}
fn same_native<P>(o:&Observation<P>,old:&Offered,at:i64)->bool {
    o.native_epoch==old.native_epoch && o.native_revision==old.native_revision
        && o.execution_generation==old.execution_generation && o.recovery_ready
        && o.grant==old.state.grant && o.grant.as_ref().is_some_and(|g|g.expires_at>at)
        && match old.state.phase {
            Phase::Active=>o.phase==LocalPhase::Active && (old.state.execution==ExecutionState::Offline||o.execution_enabled),
            Phase::Pending=>o.phase==LocalPhase::Pending,
            _=>true,
        }
}
fn draining(old:&Projected)->Projected {
    Projected{phase:Phase::Draining,execution:ExecutionState::Offline,authority_epoch:old.authority_epoch,
        grant:old.grant.clone(),drained_grant:None}
}
