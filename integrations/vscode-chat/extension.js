'use strict';
const vscode = require('vscode');
const fs = require('node:fs');
const path = require('node:path');
const {execFile} = require('node:child_process');
const {Transport} = require('./transport');
const {createHandler} = require('./handler');
const {registerReview} = require('./review');
const {registerSetup, registerSetupUri} = require('./setup');

/** Register the local Hub participant, setup controls, and review commands for this extension. */
function activate(context) {
  const runtime = JSON.parse(fs.readFileSync(path.join(context.extensionPath, 'runtime.json'), 'utf8'));
  const connections = new Set();
  context.subscriptions.push({dispose() { for (const client of connections) client.dispose(); connections.clear(); }});
  /** Open and initialize one pinned Hub stdio connection and track it for disposal. */
  const connect = async () => {
    const client = new Transport(runtime);
    connections.add(client);
    const dispose = client.dispose.bind(client);
    client.dispose = () => { connections.delete(client); dispose(); };
    try { await client.initialize(); return client; }
    catch (error) { client.dispose(); throw error; }
  };
  /** Execute a pinned operator CLI action with bounded output and timeout. */
  const run = (args, cwd) => new Promise((resolve, reject) => {
    // This path belongs to the UI participant, never to an AI-callable MCP tool.
    const prefix = runtime.args.slice(0, runtime.args.indexOf('mcp'));
    execFile(runtime.command, [...prefix, ...args], {cwd, timeout: args[0] === 'setup' ? 180000 : 60000, maxBuffer: 16 * 1024 * 1024},
      (error, stdout, stderr) => error ? reject(new Error(stderr || error.message)) : resolve(stdout));
  });
  registerReview(vscode, context, connect, run);
  registerSetup(vscode, context, runtime, run);
  registerSetupUri(vscode, context);
  if (!vscode.chat || typeof vscode.chat.createChatParticipant !== 'function') {
    vscode.window.showErrorMessage('This IDE does not yet support the VS Code Chat Participant API; @hub is unavailable.');
    return;
  }
  const handler = createHandler(vscode, connect, undefined, run);
  context.subscriptions.push(vscode.chat.createChatParticipant('multi-agents.hub', handler));
}
module.exports = {activate};
