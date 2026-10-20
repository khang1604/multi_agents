'use strict';
const vscode = require('vscode');
const fs = require('node:fs');
const path = require('node:path');
const {execFile} = require('node:child_process');
const {Transport} = require('./transport');
const {createHandler} = require('./handler');

function activate(context) {
  if (!vscode.chat || typeof vscode.chat.createChatParticipant !== 'function') {
    vscode.window.showErrorMessage('IDE này chưa hỗ trợ Chat Participant API của VS Code; @hub chưa khả dụng.');
    return;
  }
  const runtime = JSON.parse(fs.readFileSync(path.join(context.extensionPath, 'runtime.json'), 'utf8'));
  const connections = new Set();
  context.subscriptions.push({dispose() { for (const client of connections) client.dispose(); connections.clear(); }});
  const handler = createHandler(vscode, async () => {
    const client = new Transport(runtime);
    connections.add(client);
    const dispose = client.dispose.bind(client);
    client.dispose = () => { connections.delete(client); dispose(); };
    try { await client.initialize(); return client; }
    catch (error) { client.dispose(); throw error; }
  }, undefined, (args, cwd) => new Promise((resolve, reject) => {
    // This path belongs to the UI participant, never to an AI-callable MCP tool.
    const prefix = runtime.args.slice(0, runtime.args.indexOf('mcp'));
    execFile(runtime.command, [...prefix, ...args], {cwd, timeout: 60000, maxBuffer: 1024 * 1024},
      (error, stdout, stderr) => error ? reject(new Error(stderr || error.message)) : resolve(stdout));
  }));
  context.subscriptions.push(vscode.chat.createChatParticipant('multi-agents.hub', handler));
}
module.exports = {activate};
