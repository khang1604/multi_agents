'use strict';
const {spawn} = require('node:child_process');

// Only the pinned local stdio server is launched. Never invoke a shell or a model.
class Transport {
  /** Initialize bounded request state and launch only the pinned local stdio process. */
  constructor(runtime, spawnProcess = spawn) {
    this.pending = new Map();
    this.sequence = 0;
    this.buffer = '';
    this.closed = false;
    this.child = spawnProcess(runtime.command, runtime.args, {
      shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
      env: {...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8'}
    });
    this.child.stdout.setEncoding('utf8');
    this.child.stdout.on('data', chunk => this.receive(chunk));
    // Do not display/store raw stderr; it may contain provider details.
    this.child.stderr.resume();
    this.child.on('error', () => this.fail(new Error('Could not start Hub. Run global setup again.')));
    this.child.on('exit', () => this.fail(new Error('Hub connection closed.')));
    this.child.stdin.on('error', () => this.fail(new Error('Could not write the request to Hub.')));
  }
  /** Reject and clear pending requests after connection failure without exposing raw stderr. */
  fail(error) {
    this.closed = true;
    for (const entry of this.pending.values()) { clearTimeout(entry.timer); entry.reject(error); }
    this.pending.clear();
  }
  /** Parse bounded newline-delimited JSON-RPC output and resolve matching requests. */
  receive(chunk) {
    this.buffer += chunk;
    if (Buffer.byteLength(this.buffer, 'utf8') > 2 * 1024 * 1024) {
      this.fail(new Error('Hub response exceeded the limit.')); this.dispose(); return;
    }
    let end;
    while ((end = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, end); this.buffer = this.buffer.slice(end + 1);
      let reply;
      try { reply = JSON.parse(line); }
      catch { this.fail(new Error('Hub returned invalid protocol data.')); this.dispose(); return; }
      const entry = this.pending.get(reply.id);
      if (!entry) continue;
      clearTimeout(entry.timer); this.pending.delete(reply.id);
      if (reply.error) entry.reject(new Error('Hub rejected the protocol request.'));
      else entry.resolve(reply.result);
    }
  }
  /** Send one JSON-RPC request and bound how long it may wait for a response. */
  request(method, params = {}) {
    if (this.closed) return Promise.reject(new Error('Hub connection closed.'));
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error('Hub has not responded. Use /status before resubmitting to avoid duplicate tasks.'));
      }, 20000);
      this.pending.set(id, {resolve, reject, timer});
      this.child.stdin.write(JSON.stringify({jsonrpc: '2.0', id, method, params}) + '\n');
    });
  }
  /** Perform the MCP handshake and send the initialized notification. */
  async initialize() {
    await this.request('initialize', {protocolVersion: '2024-11-05', capabilities: {},
      clientInfo: {name: 'multi-agents-vscode-chat', version: '0.1.0'}});
    this.child.stdin.write(JSON.stringify({jsonrpc: '2.0', method: 'notifications/initialized'}) + '\n');
  }
  /** Invoke a Hub tool and parse only the bounded structured text result. */
  async call(name, args = {}) {
    const result = await this.request('tools/call', {name, arguments: args});
    if (result.isError) {
      const message = (result.content || []).filter(item => item.type === 'text').map(item => item.text).join(' ');
      throw new Error(message.slice(0, 1200) || 'Hub rejected the operation.');
    }
    const payload = (result.content || []).find(item => item.type === 'text');
    if (!payload) throw new Error('Hub returned no result.');
    return JSON.parse(payload.text);
  }
  /** Close the monitoring connection while retaining durable Hub checkpoints. */
  dispose() {
    this.fail(new Error('Monitoring connection closed; checkpoints are retained.'));
    this.child.stdin.end();
    if (this.child.exitCode === null) this.child.kill();
  }
}
module.exports = {Transport};
