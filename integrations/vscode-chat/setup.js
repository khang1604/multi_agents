'use strict';
const {randomBytes} = require('node:crypto');

// Serialized into the webview; no remote resources or host model access.
/** Render Quick Setup, preserve draft choices, and send explicit operator actions to the extension. */
function setupClient() {
  const api = acquireVsCodeApi();
  const box = document.getElementById('agents'), actions = document.getElementById('actions');
  const status = document.getElementById('status'), apply = document.getElementById('apply');
  const refresh = document.getElementById('refresh');
  const agentChoices = new Map(), actionChoices = new Map();
  let busy = true;
  /** Enable controls according to busy state, CLI availability, and selected providers. */
  function updateButtons() {
    for (const button of document.querySelectorAll('button')) {
      button.disabled = busy || button.dataset.unavailable === 'true';
    }
    apply.disabled = busy || ![...box.querySelectorAll('input')].some(input => input.checked);
    box.setAttribute('aria-busy', String(busy));
  }
  /** Create a labeled checkbox backed by the current unsaved selection map. */
  function makeCheck(name, text, checked, parent, choices) {
    const label = document.createElement('label'), input = document.createElement('input');
    input.type = 'checkbox'; input.dataset.name = name;
    input.checked = choices.has(name) ? choices.get(name) : checked;
    choices.set(name, input.checked);
    input.addEventListener('change', () => { choices.set(name, input.checked); updateButtons(); });
    label.append(input, document.createTextNode(' ' + text)); parent.append(label);
  }
  /** Send one setup action while suppressing duplicate clicks during an active request. */
  function send(message) {
    if (busy) return;
    busy = true; updateButtons(); api.postMessage(message);
  }
  window.addEventListener('message', ({data}) => {
    if (data.type === 'plan') {
      box.replaceChildren(); actions.replaceChildren();
      for (const agent of data.value.agents) {
        const row = document.createElement('div'); row.className = 'row';
        makeCheck(agent.agent, agent.agent, agent.enabled === true, row, agentChoices);
        const state = document.createElement('div'); state.className = 'state';
        const headline = document.createElement('span');
        headline.textContent = agent.state + ' · ' + (agent.authentication || 'UNKNOWN');
        const hint = document.createElement('small'); hint.className = 'muted';
        hint.textContent = agent.reason || (agent.authentication === 'UNKNOWN'
          ? 'Authentication is unverified. Login opens the official CLI; it may already have a session.'
          : agent.authentication === 'AUTHENTICATED' ? 'Existing CLI login detected. No login needed.' : 'Sign in through the official CLI.');
        state.append(headline, hint); row.append(state);
        const button = document.createElement('button'); button.className = 'auth-action';
        const authenticated = agent.authentication === 'AUTHENTICATED';
        button.textContent = authenticated ? 'Sign out' : 'Login';
        button.dataset.unavailable = String(agent.state === 'NOT_INSTALLED');
        button.setAttribute('aria-label', (authenticated ? 'Sign out of ' : 'Log in to ') + agent.agent);
        if (agent.state === 'NOT_INSTALLED') button.title = 'Install this official CLI first.';
        button.addEventListener('click', () => send({type: authenticated ? 'logout' : 'login', provider: agent.agent}));
        row.append(button); box.append(row);
      }
      const labels = {launcher: 'Install / update the ma command', chat: 'Connect VS Code @hub', mcp: 'Connect VS Code MCP'};
      if (document.body.dataset.windows === 'true') labels.wake = 'Automatic queue wake';
      for (const [key, label] of Object.entries(labels)) {
        makeCheck(key, label, data.value.actions[key] === true, actions, actionChoices);
      }
      status.textContent = data.message || 'Scan complete. Only selected options will be applied.';
      busy = false; updateButtons();
    } else if (data.type === 'busy' || data.type === 'result') {
      status.textContent = data.message;
      busy = data.type === 'busy'; updateButtons();
    }
  });
  apply.addEventListener('click', () => {
    const providers = [...box.querySelectorAll('input')].filter(input => input.checked).map(input => input.dataset.name);
    const selected = {};
    for (const input of actions.querySelectorAll('input')) selected[input.dataset.name] = input.checked;
    send({type: 'apply', providers, actions: selected});
  });
  refresh.addEventListener('click', () => send({type: 'refresh'}));
  updateButtons(); api.postMessage({type: 'refresh'});
}

/** Build the English setup page with nonce-scoped scripts/styles and no remote resources. */
function setupHtml(nonce, windows) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style nonce="${nonce}">
body{max-width:850px;margin:32px auto;padding:0 24px;color:var(--vscode-foreground);background:var(--vscode-editor-background);font:14px var(--vscode-font-family)}h1{font-size:26px;margin-bottom:8px}.muted{color:var(--vscode-descriptionForeground)}section{border:1px solid var(--vscode-panel-border);padding:18px;border-radius:8px;margin:18px 0}.row{display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--vscode-panel-border)}.row label{min-width:140px}.state{flex:1;min-width:0;overflow-wrap:anywhere}.state small{display:block;margin-top:5px;line-height:1.4}.auth-action{min-width:88px}button{padding:8px 14px;border:0;border-radius:3px;cursor:pointer;background:var(--vscode-button-background);color:var(--vscode-button-foreground)}button:disabled{opacity:.5;cursor:default}.actions{display:grid;grid-template-columns:1fr 1fr;gap:14px}.footer{display:flex;flex-wrap:wrap;gap:12px;align-items:center}#status{white-space:pre-wrap;padding:12px 0}input{accent-color:var(--vscode-focusBorder)}:focus-visible{outline:2px solid var(--vscode-focusBorder);outline-offset:3px}details{margin-top:18px}@media(max-width:600px){.actions{grid-template-columns:1fr}.row{flex-wrap:wrap}.row label{min-width:110px}.state{flex-basis:calc(100% - 130px)}}
</style></head><body data-windows="${windows}">
<h1>Multi Agents — Quick Setup</h1><p class="muted">Select the CLIs and integrations you need. Apply once, with backups. No model calls.</p>
<section><strong>1. Agents</strong><div id="agents" aria-busy="true">Checking CLIs and authentication status…</div>
<p class="muted">Existing logins are checked automatically. Agent selection controls orchestration; Login and Sign out remain available for unselected agents. Install missing CLIs first.</p>
<p class="muted">Default model: <strong>INHERIT</strong> for all agents. UNKNOWN means unverified, not signed out. Authentication does not confirm quota.</p></section>
<section><strong>2. Integrations</strong><div class="actions" id="actions"></div></section>
<div class="footer"><button id="apply" disabled>Apply once</button><button id="refresh" disabled>Check CLIs again</button></div><div role="status" aria-live="polite" id="status"></div>
<details><summary>Advanced</summary><p>Use <code>ma setup --advanced</code> to choose individual models/roles or another MCP client. Source, synthetic data and APIs are confirmed separately with <code>ma init</code> in each project.</p></details>
<script nonce="${nonce}">(${setupClient.toString()})();</script></body></html>`;
}

/** Connect setup messages to pinned CLI tasks and refresh authentication after task completion. */
function registerSetup(api, context, runtime, run) {
  context.subscriptions.push(api.commands.registerCommand('multi-agents.setup', () => {
    const panel = api.window.createWebviewPanel('multi-agents-setup', 'Multi Agents — Quick Setup', api.ViewColumn.One,
      {enableScripts: true, localResourceRoots: []});
    panel.webview.html = setupHtml(randomBytes(18).toString('hex'), process.platform === 'win32');
    let busy = false, disposed = false, authTask;
    /** Post a setup update only while its webview panel is still open. */
    const post = message => { if (!disposed) panel.webview.postMessage(message); };
    /** Run official non-generative CLI status probes and publish the resulting setup plan. */
    async function scan(message) {
      post({type: 'busy', message: 'Checking existing CLI logins with official status probes; no model calls…'});
      const value = JSON.parse(await run(['setup', '--plan', '--json']));
      post({type: 'plan', value, message});
    }
    /** Handle only the matching auth task completion and trigger one status refresh. */
    function finish(execution, exitCode) {
      if (!authTask || (execution.task !== authTask && execution.task.definition?.requestId !== authTask.definition?.requestId)) return;
      authTask = undefined;
      void (async () => {
        try {
          const message = exitCode === 0 ? 'Authentication process ended. Status has been checked again.'
            : 'Authentication process failed or was cancelled. Status has been checked again; inspect the terminal.';
          await scan(message);
        } catch (error) { post({type: 'result', message: 'Hub: ' + error.message}); }
        finally { busy = false; }
      })();
    }
    const finished = api.tasks.onDidEndTaskProcess(event => finish(event.execution, event.exitCode));
    const ended = api.tasks.onDidEndTask(event => finish(event.execution));
    context.subscriptions.push(finished, ended);
    panel.onDidDispose(() => { disposed = true; finished.dispose(); ended.dispose(); });
    panel.webview.onDidReceiveMessage(async message => {
      if (disposed || busy) return;
      busy = true;
      let launched = false;
      try {
        if (message.type === 'refresh') {
          await scan();
        } else if (message.type === 'apply') {
          post({type: 'busy', message: 'Applying selected options and keeping backups…'});
          const value = JSON.parse(await run(['setup', '--apply-options', JSON.stringify({providers: message.providers, actions: message.actions}), '--json']));
          post({type: 'result', message: 'Setup complete. Model: INHERIT. Backup: ' + (value.backup || 'saved') + '\nNext: open your project → ma init → @hub PROMPT.'});
        } else if (message.type === 'login' || message.type === 'logout') {
          if (!['codex', 'claude', 'copilot', 'antigravity'].includes(message.provider)) throw new Error('Invalid provider');
          const signingOut = message.type === 'logout';
          const prefix = runtime.args.slice(0, runtime.args.indexOf('mcp'));
          const task = new api.Task({type: 'multi-agents-auth', requestId: randomBytes(12).toString('hex')}, api.TaskScope.Global,
            (signingOut ? 'Sign out ' : 'Login ') + message.provider, 'Multi Agents',
            new api.ProcessExecution(runtime.command, [...prefix, 'setup', signingOut ? '--logout' : '--login', message.provider],
              {cwd: require('node:os').tmpdir(), env: {PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8'}}));
          authTask = task;
          const interactiveLogout = signingOut && ['copilot', 'antigravity'].includes(message.provider);
          post({type: 'busy', message: interactiveLogout
            ? 'In the official CLI terminal, enter /logout, then exit. Status refreshes automatically when the process ends.'
            : signingOut ? 'Signing out through the official CLI. Status refreshes automatically when it ends.'
            : 'Complete login in the official CLI terminal. Existing verified logins are reused. Status refreshes automatically when it ends.'});
          launched = true;
          await api.tasks.executeTask(task);
        }
      } catch (error) {
        authTask = undefined;
        launched = false;
        post({type: 'result', message: 'Hub: ' + error.message});
      } finally { if (!launched) busy = false; }
    }, undefined, context.subscriptions);
  }));
}

/** Accept only the fixed setup deep link without applying settings or accepting commands. */
function registerSetupUri(api, context) {
  context.subscriptions.push(api.window.registerUriHandler({
    async handleUri(uri) {
      if (uri.scheme !== api.env.uriScheme || uri.authority !== 'khang1604.multi-agents-chat'
          || uri.path !== '/setup' || uri.query || uri.fragment) return;
      await api.commands.executeCommand('multi-agents.setup');
    }
  }));
}
module.exports = {registerSetup, registerSetupUri, setupHtml};
