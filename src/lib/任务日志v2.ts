/** Decode each output stream incrementally; UTF-8 boundaries must not corrupt
 * Chinese text, and repeated/stale poll responses must not duplicate output. */
export interface TaskLogPage {
  data_base64: string; requested_cursor: number; cursor: number;
  next_cursor: number; dropped_bytes: number; has_more: boolean;
}
export class TaskLogCursor {
  cursor = 0;
  text = "";
  displayTruncated = false;
  private decoder = new TextDecoder();
  constructor(private readonly displayLimit = 131072) {}

  append(page: TaskLogPage, terminal: boolean): boolean {
    if (page.requested_cursor !== this.cursor) return false;
    const counts = [page.cursor, page.next_cursor, page.dropped_bytes];
    if (counts.some((n) => !Number.isSafeInteger(n) || n < 0)
      || page.cursor < this.cursor || page.next_cursor < page.cursor
      || page.dropped_bytes !== page.cursor - this.cursor) throw new Error("无效的任务日志游标");
    const bytes = Uint8Array.from(atob(page.data_base64), (c) => c.charCodeAt(0));
    if (bytes.length !== page.next_cursor - page.cursor) throw new Error("任务日志长度不匹配");
    if (page.dropped_bytes) {
      this.decoder = new TextDecoder();
      this.text += `\n[日志环形缓冲已丢弃 ${page.dropped_bytes} 字节]\n`;
    }
    this.text += this.decoder.decode(bytes, { stream: !terminal || page.has_more });
    if (this.text.length > this.displayLimit) {
      this.text = this.text.slice(-this.displayLimit);
      this.displayTruncated = true;
    }
    this.cursor = page.next_cursor;
    return true;
  }
}
