use crate::common::{identity, Fixture};
use coding_tools_cloud_gateway::{
    device::{enrollment_message, EnrolledDevice},
    projection::*,
    OAuthPrincipal,
};
use ring::signature::{Ed25519KeyPair, KeyPair};
use uuid::Uuid;
pub struct Harness {
    pub f: Fixture,
    pub projection: ProjectionStore,
    pub key: Ed25519KeyPair,
    pub device: EnrolledDevice,
    pub a: ConversationBinding,
    pub b: ConversationBinding,
    pub lease: LocalLease,
}
impl Harness {
    pub async fn new() -> Self {
        let f = Fixture::new().await;
        let key = Ed25519KeyPair::from_seed_unchecked(&[9; 32]).unwrap();
        let invitation = f.store.create_device_invitation().await.unwrap();
        let proof = key.sign(
            &enrollment_message(
                &identity(),
                invitation.token.expose(),
                key.public_key().as_ref(),
            )
            .unwrap(),
        );
        let device = f
            .store
            .redeem_device_invitation(
                invitation.token.expose(),
                key.public_key().as_ref(),
                proof.as_ref(),
            )
            .await
            .unwrap();
        let projection = ProjectionStore::activate(f.store.clone()).await.unwrap();
        projection.bind_device(device.id).await.unwrap();
        let principal = OAuthPrincipal {
            subject: Uuid::from_u128(8),
            client_id: "public-client".into(),
            resource: identity().resource(),
        };
        let a = projection
            .conversation_binding(&principal, "host-session-A")
            .unwrap();
        let b = projection
            .conversation_binding(&principal, "host-session-B")
            .unwrap();
        let at = clock(&f).await;
        let lease = LocalLease {
            id: Uuid::from_u128(30),
            conversation: a.as_str().into(),
            issued_at: at,
            expires_at: at + 600,
            scopes: vec!["files.read".into()],
        };
        Self {
            f,
            projection,
            key,
            device,
            a,
            b,
            lease,
        }
    }
    pub async fn claims(
        &self,
        revision: i64,
        phase: ProjectionPhase,
        execution: ExecutionState,
    ) -> ProjectionClaims {
        let challenge = self.projection.challenge(self.device.id).await.unwrap();
        let at = clock(&self.f).await;
        ProjectionClaims {
            version: 1,
            issuer: identity().issuer(),
            resource: identity().resource(),
            connector: identity().connector(),
            device: self.device.id,
            device_epoch: self.device.epoch,
            gateway_boot: challenge.gateway_boot,
            challenge: challenge.nonce.expose().into(),
            revision,
            authority_epoch: 1,
            issued_at: at,
            valid_until: at + 60,
            phase,
            execution,
            grant: if phase == ProjectionPhase::Free {
                None
            } else {
                Some(self.lease.clone())
            },
            drained_grant: None,
        }
    }
    pub fn signed(&self, c: &ProjectionClaims) -> (Vec<u8>, Vec<u8>) {
        let bytes = serde_json::to_vec(c).unwrap();
        let sig = self.key.sign(&projection_message(&bytes).unwrap());
        (bytes, sig.as_ref().to_vec())
    }
    pub async fn apply(
        &self,
        c: &ProjectionClaims,
    ) -> coding_tools_cloud_gateway::Result<ApplyOutcome> {
        let (p, s) = self.signed(c);
        self.projection.apply(self.device.id, &p, &s).await
    }
    pub async fn active(&self) -> ProjectionClaims {
        let c = self
            .claims(1, ProjectionPhase::Active, ExecutionState::Online)
            .await;
        assert_eq!(self.apply(&c).await.unwrap(), ApplyOutcome::Applied);
        c
    }
    pub async fn drain_free(&self) {
        let d = self
            .claims(2, ProjectionPhase::Draining, ExecutionState::Offline)
            .await;
        self.apply(&d).await.unwrap();
        let mut f = self
            .claims(3, ProjectionPhase::Free, ExecutionState::Offline)
            .await;
        f.drained_grant = Some(self.lease.id);
        self.apply(&f).await.unwrap();
    }
}
pub async fn clock(f: &Fixture) -> i64 {
    sqlx::query_scalar("SELECT floor(extract(epoch FROM clock_timestamp()))::bigint")
        .fetch_one(&f.pool)
        .await
        .unwrap()
}
