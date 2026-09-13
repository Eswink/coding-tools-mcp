export interface SessionPolicy {
  exclusive: boolean;
  access_token_ttl_seconds: number;
  refresh_session_ttl_seconds: number;
  chat_lease_ttl_seconds: number;
  chat_idle_timeout_seconds: number;
}
export function sessionPolicy(input?: Partial<SessionPolicy>): SessionPolicy {
  return { exclusive: true, access_token_ttl_seconds: 3600,
    refresh_session_ttl_seconds: 30 * 86400, chat_lease_ttl_seconds: 86400,
    chat_idle_timeout_seconds: 0, ...input };
}
export function validateSessionPolicy(p: SessionPolicy): string {
  if (typeof p.exclusive !== "boolean") return "独占设置必须为布尔值";
  const ranges: [keyof SessionPolicy, number, number][] = [
    ["access_token_ttl_seconds", 300, 28800],
    ["refresh_session_ttl_seconds", 86400, 90 * 86400],
    ["chat_lease_ttl_seconds", 3600, 30 * 86400],
  ];
  for (const [key, min, max] of ranges) {
    const value = p[key];
    if (typeof value !== "number" || !Number.isSafeInteger(value) || value < min || value > max) {
      return `${key} 必须为 ${min}～${max} 秒的整数`;
    }
  }
  const idle = p.chat_idle_timeout_seconds;
  if (!Number.isSafeInteger(idle) || (idle !== 0 && (idle < 1800 || idle > 86400))) return "空闲时限必须关闭或为 30～1440 分钟";
  if (idle > p.chat_lease_ttl_seconds) return "空闲时限不得大于聊天授权时限";
  return "";
}
export function policyFromFields(exclusive: boolean, accessMinutes: number | undefined,
  refreshDays: number | undefined, leaseHours: number | undefined, idleMinutes: number | undefined): SessionPolicy {
  if (![accessMinutes, refreshDays, leaseHours, idleMinutes].every(Number.isSafeInteger)) throw new Error("请填写整数时长，不能留空或使用小数");
  const p = { exclusive, access_token_ttl_seconds: accessMinutes! * 60,
    refresh_session_ttl_seconds: refreshDays! * 86400, chat_lease_ttl_seconds: leaseHours! * 3600,
    chat_idle_timeout_seconds: idleMinutes! * 60 };
  const error = validateSessionPolicy(p); if (error) throw new Error(error); return p;
}
