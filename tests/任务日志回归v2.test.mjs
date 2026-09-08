import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { TaskLogCursor } = require(path.resolve(process.env.TASK_LOG_MODULE ?? '/tmp/任务日志编译v2/任务日志v2.js'));
function page(bytes, requested=0, offset=requested, more=false) {
  return {data_base64: Buffer.from(bytes).toString('base64'), requested_cursor:requested, cursor:offset,
    next_cursor: offset+bytes.length, dropped_bytes:offset-requested, has_more:more};
}
test('中文跨字节页保真', () => {
  const log = new TaskLogCursor(); const b=Buffer.from('中文输出');
  for(let i=0;i<b.length;i+=2) log.append(page(b.subarray(i,i+2),i,i,i+2<b.length),true);
  assert.equal(log.text,'中文输出'); assert.equal(log.cursor,b.length);
});
test('重复或迟到页不复制输出',()=>{ const log=new TaskLogCursor(); const p=page(Buffer.from('ok')); log.append(p,true); assert.equal(log.append(p,true),false); assert.equal(log.text,'ok'); });
test('stdout stderr游标独立',()=>{const a=new TaskLogCursor(), b=new TaskLogCursor();a.append(page(Buffer.from('out')),false);b.append(page(Buffer.from('e')),true);assert.equal(a.cursor,3);assert.equal(b.cursor,1);});
test('环形丢弃明确提示且游标继续',()=>{const log=new TaskLogCursor();log.append(page(Buffer.from('tail'),0,16),true);assert.match(log.text,/丢弃 16 字节/);assert.equal(log.cursor,20);});
test('非法范围拒绝且不改变游标',()=>{const log=new TaskLogCursor();assert.throws(()=>log.append({...page(Buffer.from('x')),next_cursor:0},true));assert.equal(log.cursor,0);});
test('UI显示有界且仍保留绝对游标',()=>{const log=new TaskLogCursor(4);log.append(page(Buffer.from('0123456789')),true);assert.equal(log.text,'6789');assert.equal(log.cursor,10);assert.equal(log.displayTruncated,true);});
test('空终态页不重复UTF8或改变状态',()=>{const log=new TaskLogCursor();log.append(page(Buffer.from('好')),true);log.append(page(Buffer.alloc(0),3),true);assert.equal(log.text,'好');assert.equal(log.cursor,3);});
test('新的任务使用新解码器和零游标',()=>{const old=new TaskLogCursor();old.append(page(Buffer.from('旧任务')),true);const next=new TaskLogCursor();assert.equal(next.cursor,0);assert.equal(next.text,'');});
