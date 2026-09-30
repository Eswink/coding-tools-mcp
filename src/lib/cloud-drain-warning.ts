/** Register once per layout lifetime; never expose native event payloads. */
export function watchCloudDrain(
  listen: (event: string, callback: () => void) => Promise<() => void>,
  warn: (message: string) => void,
) {
  let disposed = false, warned = false;
  let unlisten: (() => void) | undefined;
  void listen('cloud-drain-incomplete', () => {
    if (disposed || warned) return;
    warned = true;
    warn('云连接尚未安全排空，应用暂未退出。请在本机检查仍在运行或状态未知的任务；不要强制接管或重新初始化日志。已执行的操作不会回滚。');
  }).then(stop => { if (disposed) stop(); else unlisten = stop; }).catch(() => {
    if (!disposed) warn('无法订阅云连接退出警告。退出前请在工作区检查云连接与未完成任务的本机状态。');
  });
  return () => { disposed = true; unlisten?.(); };
}
