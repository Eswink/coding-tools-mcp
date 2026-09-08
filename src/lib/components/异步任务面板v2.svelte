<script lang="ts">
  import { confirm } from "@tauri-apps/plugin-dialog";
  import { listTasks, getTask, cancelTask, type TaskChannel, type TaskSummary, type TaskDetails } from "$lib/api/异步任务v2";
  import { TaskLogCursor } from "$lib/任务日志v2";

  let { workspaceId, channel, maxTimeoutMs = 86400000, onBudgetSave }: {
    workspaceId: string; channel: TaskChannel; maxTimeoutMs?: number; onBudgetSave: (ms: number) => Promise<void>;
  } = $props();
  let jobs = $state<TaskSummary[]>([]);
  let selected = $state("");
  let detail = $state<TaskDetails | null>(null);
  let output = $state(""); let errors = $state(""); let truncated = $state(false);
  let failure = $state(""); let busy = $state(false); let saving = $state(false);
  let minutes = $state(1440);
  let out = new TaskLogCursor(); let err = new TaskLogCursor();
  const labels: Record<string, string> = { queued:"已受理", running:"运行中", cancelling:"取消中", succeeded:"成功", failed:"失败", timed_out:"执行超时", cancelled:"已取消", interrupted:"执行器已中断" };

  $effect(() => { minutes = Math.ceil(maxTimeoutMs / 60000); });
  $effect(() => {
    // Deliberately bind reset to selection AND namespace, not to every poll.
    const key = `${workspaceId}/${channel}/${selected}`;
    void key;
    out = new TaskLogCursor(); err = new TaskLogCursor();
    output = ""; errors = ""; detail = null; truncated = false;
  });
  $effect(() => {
    const id = workspaceId; const service = channel;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    jobs = []; selected = ""; failure = "";
    async function poll() {
      try {
        if (!document.hidden) {
          const response = await listTasks(id, service);
          if (disposed) return;
          jobs = response.jobs;
          if (!jobs.some((job) => job.job_id === selected)) selected = jobs[0]?.job_id ?? "";
          const jobId = selected;
          const currentOut = out; const currentErr = err;
          if (jobId) {
            const result = await getTask(id, service, jobId, currentOut.cursor, currentErr.cursor);
            if (disposed || selected !== jobId || out !== currentOut) return;
            currentOut.append(result.stdout, result.terminal);
            currentErr.append(result.stderr, result.terminal);
            detail = result; output = currentOut.text; errors = currentErr.text;
            truncated = currentOut.displayTruncated || currentErr.displayTruncated;
          }
          failure = "";
        }
      } catch (error) { if (!disposed) failure = String(error); }
      finally { if (!disposed) timer = setTimeout(poll, 1500); }
    }
    void poll();
    return () => { disposed = true; if (timer) clearTimeout(timer); };
  });

  async function stop(confirmTerminated = false) {
    const id = workspaceId; const service = channel; const jobId = selected;
    if (!jobId || busy) return;
    const approved = await confirm(confirmTerminated
      ? "仅在你已核查旧进程全部停止后确认。此操作不终止未知进程，也不会将任务标记为成功或重跑命令。"
      : "取消此任务及其受管子进程？已经发生的文件修改等副作用不会撤销。", {title:"任务取消确认", kind:"warning"});
    if (!approved || id !== workspaceId || service !== channel || selected !== jobId) return;
    busy = true;
    try { await cancelTask(id, service, jobId, confirmTerminated); }
    catch (error) { if (id === workspaceId && service === channel) failure = String(error); }
    finally { busy = false; }
  }

  async function saveBudget() {
    if (!Number.isInteger(minutes) || minutes < 1 || minutes > 1440) {
      failure = "任务预算上限须为1至1440整数分钟。"; return;
    }
    saving = true;
    try { await onBudgetSave(minutes * 60000); }
    catch (error) { failure = String(error); }
    finally { saving = false; }
  }
</script>

<section class="tx-card mt-4 space-y-4 p-5" aria-label="异步命令任务">
  <header><h3 class="font-semibold">异步任务 · {channel.toUpperCase()}</h3>
    <p class="mt-1 text-sm opacity-70">HTTP超时不是任务失败。使用同一个 request_id 找回任务，不要盲目重跑。重启恢复记录不代表进程继续执行。</p>
  </header>
  <div class="flex flex-wrap items-end gap-3">
    <label class="text-sm">新任务执行预算上限（分钟）
      <input class="tx-input mt-1 block w-36" type="number" min="1" max="1440" step="1" bind:value={minutes} />
    </label>
    <button class="tx-btn" disabled={saving} onclick={saveBudget}>{saving ? "保存中…" : "保存上限"}</button>
    <span class="text-xs opacity-60">默认提交10分钟；最大24小时；保存后重启对应服务生效，不修改运行中的任务。</span>
  </div>
  {#if failure}<p class="rounded border p-3 text-sm" role="alert">{failure}</p>{/if}
  {#if jobs.length === 0}<p class="py-4 text-sm opacity-60">暂无任务。通过 MCP／Actions 的 start_exec_task 提交；此面板不会自动启动命令。</p>{/if}
  <div class="grid gap-3 md:grid-cols-[minmax(180px,1fr)_minmax(0,3fr)]">
    <div class="max-h-96 space-y-2 overflow-auto" aria-label="任务列表">
      {#each jobs as job (job.job_id)}
        <button class="w-full rounded border p-3 text-left text-sm" class:font-semibold={selected === job.job_id}
          aria-pressed={selected === job.job_id} onclick={() => selected = job.job_id}>
          <span class="block break-all">{job.request_id}</span>
          <span class="mt-1 block text-xs opacity-70">{labels[job.status] ?? job.status} · {Math.round(job.elapsed_ms / 1000)}秒</span>
        </button>
      {/each}
    </div>
    {#if detail}
      <div class="min-w-0 space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="text-sm"><strong>{labels[detail.status] ?? detail.status}</strong>
            <span class="ml-2 opacity-60">退出码：{detail.result?.exit_code ?? "—"}</span>
            <p class="mt-1 break-all font-mono text-xs opacity-60">{detail.job_id}</p>
          </div>
          {#if !detail.terminal}<button class="tx-btn" disabled={busy} onclick={() => stop()}>请求取消</button>{/if}
          {#if detail.terminal && detail.result?.process_may_be_running}
            <button class="tx-btn" disabled={busy} onclick={() => stop(true)}>已人工确认旧进程停止</button>
          {/if}
        </div>
        {#if detail.result?.error}<p role="alert" class="break-all text-sm">{detail.result.error.code ?? "任务失败"}：{detail.result.error.message ?? "请检查任务日志"}</p>{/if}
        {#if detail.result?.message}<p class="break-all text-sm">{detail.result.message}</p>{/if}
        {#if detail.persistence_failed}<p role="alert" class="text-sm">任务快照保存失败；不要自动重试命令，请保留当前结果并检查系统凭据库／磁盘。</p>{/if}
        {#if detail.result?.output_complete === false}<p class="text-sm">输出未完整收集；中断或读取失败可能丢失末尾输出。</p>{/if}
        {#if truncated}<p class="text-xs opacity-60">面板只显示日志尾部；完整保留范围可通过字节游标分批读取。</p>{/if}
        <div><h4 class="text-xs font-semibold">stdout</h4><pre class="mt-1 max-h-64 overflow-auto rounded border p-3 text-xs whitespace-pre-wrap break-all">{output || "暂无输出"}</pre></div>
        <div><h4 class="text-xs font-semibold">stderr</h4><pre class="mt-1 max-h-48 overflow-auto rounded border p-3 text-xs whitespace-pre-wrap break-all">{errors || "暂无错误输出"}</pre></div>
      </div>
    {/if}
  </div>
  <p class="text-xs opacity-60">每通道最多4个活动任务、32条保留记录；终态默认保留1小时。取消无法撤销副作用；任务不会自动唤醒GPT会话。</p>
</section>
