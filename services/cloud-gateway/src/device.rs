use crate::{
    crypto::valid_digest, store::now, IdentityError, IdentityStore, PublicIdentity, Result, Secret,
};
use ring::signature::{UnparsedPublicKey, ED25519};
use sqlx::Row;
use uuid::Uuid;

pub struct EnrollmentInvitation {
    pub id: Uuid,
    pub token: Secret,
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EnrolledDevice {
    pub id: Uuid,
    pub connector: Uuid,
    pub public_key: Vec<u8>,
    pub epoch: i64,
}
/// The device signs this exact domain-separated payload. The invitation is never a URL parameter.
pub fn enrollment_message(
    identity: &PublicIdentity,
    invitation: &str,
    public_key: &[u8],
) -> Result<Vec<u8>> {
    if !valid_digest(invitation) || public_key.len() != 32 {
        return Err(IdentityError::InvalidProof);
    }
    let mut msg = b"coding-tools-device-enrollment-v1\0".to_vec();
    msg.extend(
        serde_json::to_vec(&(
            identity.issuer(),
            identity.connector(),
            invitation,
            public_key,
        ))
        .map_err(|_| IdentityError::InvalidProof)?,
    );
    Ok(msg)
}
impl IdentityStore {
    /// Trusted operator only. Invites do not authorize tools and expire in five minutes.
    pub async fn create_device_invitation(&self) -> Result<EnrollmentInvitation> {
        let token = Secret::random()?;
        let id = Uuid::new_v4();
        let mut tx = self.pool.begin().await?;
        let expiry = now(&mut tx).await? + 300;
        sqlx::query(
            "INSERT INTO ctm_enrollments(token_hash,id,connector,expires_at) VALUES($1,$2,$3,$4)",
        )
        .bind(self.key.digest("enrollment-v1", token.expose().as_bytes()))
        .bind(id)
        .bind(self.identity.connector())
        .bind(expiry)
        .execute(&mut *tx)
        .await?;
        tx.commit().await?;
        Ok(EnrollmentInvitation { id, token })
    }
    pub async fn redeem_device_invitation(
        &self,
        token: &str,
        public_key: &[u8],
        signature: &[u8],
    ) -> Result<EnrolledDevice> {
        let msg = enrollment_message(&self.identity, token, public_key)?;
        UnparsedPublicKey::new(&ED25519, public_key)
            .verify(&msg, signature)
            .map_err(|_| IdentityError::InvalidProof)?;
        let hash = self.key.digest("enrollment-v1", token.as_bytes());
        let mut tx = self.pool.begin().await?;
        let row=sqlx::query("SELECT id,connector,expires_at,consumed FROM ctm_enrollments WHERE token_hash=$1 FOR UPDATE")
            .bind(&hash).fetch_optional(&mut *tx).await?.ok_or(IdentityError::InvalidProof)?;
        if row.get::<bool, _>("consumed")
            || row.get::<Uuid, _>("connector") != self.identity.connector()
            || now(&mut tx).await? >= row.get::<i64, _>("expires_at")
        {
            return Err(IdentityError::InvalidProof);
        }
        let device = EnrolledDevice {
            id: Uuid::new_v4(),
            connector: self.identity.connector(),
            public_key: public_key.to_vec(),
            epoch: 1,
        };
        sqlx::query("UPDATE ctm_enrollments SET consumed=true WHERE token_hash=$1")
            .bind(hash)
            .execute(&mut *tx)
            .await?;
        sqlx::query(
            "INSERT INTO ctm_devices(id,enrollment_id,connector,public_key) VALUES($1,$2,$3,$4)",
        )
        .bind(device.id)
        .bind(row.get::<Uuid, _>("id"))
        .bind(device.connector)
        .bind(public_key)
        .execute(&mut *tx)
        .await?;
        tx.commit().await?;
        Ok(device)
    }
    pub async fn registered_device(&self, id: Uuid) -> Result<EnrolledDevice> {
        let row=sqlx::query("SELECT id,connector,public_key,epoch FROM ctm_devices WHERE id=$1 AND NOT revoked AND connector=$2")
            .bind(id).bind(self.identity.connector()).fetch_optional(&self.pool).await?.ok_or(IdentityError::InvalidProof)?;
        Ok(EnrolledDevice {
            id: row.get("id"),
            connector: row.get("connector"),
            public_key: row.get("public_key"),
            epoch: row.get("epoch"),
        })
    }
    pub async fn revoke_device(&self, id: Uuid) -> Result<()> {
        sqlx::query("UPDATE ctm_devices SET revoked=true,epoch=epoch+1 WHERE id=$1 AND connector=$2 AND NOT revoked")
            .bind(id).bind(self.identity.connector()).execute(&self.pool).await?;
        Ok(())
    }
}
