/** Explicit synthetic laboratory CLI; never point a company connector at this. */
import { startLab } from './gateway.mjs';
import { SyntheticWorkspace } from './state.mjs';

const args = process.argv.slice(2);
if (!args.includes('--lab') || args.some((arg, i) =>
  !['--lab', '--port', '--online-fixture'].includes(arg) && args[i - 1] !== '--port')) {
  console.error('Usage: MCP_LAB_TOKEN=<synthetic token> node prototypes/cloud-gateway/cli.mjs --lab [--port 28769] [--online-fixture]');
  process.exitCode = 2;
} else {
  try {
    const at = args.indexOf('--port');
    const port = at === -1 ? 28769 : Number(args[at + 1]);
    const state = new SyntheticWorkspace();
    state.approveForTest('lab-owner');
    state.setOnlineForTest(args.includes('--online-fixture'));
    const lab = await startLab({ lab: true, port, bearerToken: process.env.MCP_LAB_TOKEN, state });
    console.log(JSON.stringify({ mode: 'non-production-protocol-lab', endpoint: lab.endpoint,
      worker: args.includes('--online-fixture') ? 'synthetic-online' : 'synthetic-offline' }));
    for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => { void lab.close(); });
  } catch {
    console.error('Lab startup rejected. Check explicit mode, port and synthetic MCP_LAB_TOKEN.');
    process.exitCode = 2;
  }
}
