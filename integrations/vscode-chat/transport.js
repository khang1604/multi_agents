'use strict';
const {spawn} = require('node:child_process');

// Only the pinned local stdio server is launched. Never invoke a shell or a model.
class Transport {
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
    this.child.on('error', () => this.fail(new Error('Không mở được Hub. Chạy lại setup global.')));
    this.child.on('exit', () => this.fail(new Error('Kết nối Hub đã đóng.')));
    this.child.stdin.on('error', () => this.fail(new Error('Không ghi được yêu cầu tới Hub.')));
  }
  fail(error) {
    this.closed = true;
    for (const entry of this.pending.values()) { clearTimeout(entry.timer); entry.reject(error); }
    this.pending.clear();
  }
  receive(chunk) {
    this.buffer += chunk;
    if (Buffer.byteLength(this.buffer, 'utf8') > 2 * 1024 * 1024) {
      this.fail(new Error('Phản hồi Hub vượt giới hạn.')); this.dispose(); return;
    }
    let end;
    while ((end = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, end); this.buffer = this.buffer.slice(end + 1);
      let reply;
      try { reply = JSON.parse(line); }
      catch { this.fail(new Error('Hub trả dữ liệu giao thức không hợp lệ.')); this.dispose(); return; }
      const entry = this.pending.get(reply.id);
      if (!entry) continue;
      clearTimeout(entry.timer); this.pending.delete(reply.id);
      if (reply.error) entry.reject(new Error('Hub từ chối yêu cầu giao thức.'));
      else entry.resolve(reply.result);
    }
  }
  request(method, params = {}) {
    if (this.closed) return Promise.reject(new Error('Kết nối Hub đã đóng.'));
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error('Hub chưa trả lời. Dùng /status trước khi gửi lại để tránh tạo task trùng.'));
      }, 20000);
      this.pending.set(id, {resolve, reject, timer});
      this.child.stdin.write(JSON.stringify({jsonrpc: '2.0', id, method, params}) + '\n');
    });
  }
  async initialize() {
    await this.request('initialize', {protocolVersion: '2024-11-05', capabilities: {},
      clientInfo: {name: 'multi-agents-vscode-chat', version: '0.1.0'}});
    this.child.stdin.write(JSON.stringify({jsonrpc: '2.0', method: 'notifications/initialized'}) + '\n');
  }
  async call(name, args = {}) {
    const result = await this.request('tools/call', {name, arguments: args});
    if (result.isError) {
      const message = (result.content || []).filter(item => item.type === 'text').map(item => item.text).join(' ');
      throw new Error(message.slice(0, 1200) || 'Hub từ chối thao tác.');
    }
    const payload = (result.content || []).find(item => item.type === 'text');
    if (!payload) throw new Error('Hub không trả kết quả.');
    return JSON.parse(payload.text);
  }
  dispose() {
    this.fail(new Error('Đã đóng kết nối theo dõi; checkpoint vẫn được giữ.'));
    this.child.stdin.end();
    if (this.child.exitCode === null) this.child.kill();
  }
}
module.exports = {Transport};
