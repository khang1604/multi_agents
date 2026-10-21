'use strict';
const {randomBytes} = require('node:crypto');
function setupHtml(nonce, windows) {
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style nonce="${nonce}">body{max-width:850px;margin:32px auto;padding:0 24px;color:var(--vscode-foreground);background:var(--vscode-editor-background);font:14px var(--vscode-font-family)}h1{font-size:26px;margin-bottom:8px}.muted{color:var(--vscode-descriptionForeground)}section{border:1px solid var(--vscode-panel-border);padding:18px;border-radius:8px;margin:18px 0}.row{display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--vscode-panel-border)}.row label{min-width:140px}.state{flex:1}button{padding:8px 14px;border:0;border-radius:3px;cursor:pointer;background:var(--vscode-button-background);color:var(--vscode-button-foreground)}button:disabled{opacity:.5;cursor:default}.actions{display:grid;grid-template-columns:1fr 1fr;gap:14px}.footer{display:flex;gap:12px;align-items:center}#status{white-space:pre-wrap;padding:12px 0}input{accent-color:var(--vscode-focusBorder)}:focus-visible{outline:2px solid var(--vscode-focusBorder);outline-offset:3px}details{margin-top:18px}@media(max-width:600px){.actions{grid-template-columns:1fr}.row{flex-wrap:wrap}.row label{min-width:110px}}</style></head><body>
<h1>Multi Agents — Setup nhanh</h1><p class="muted">Chọn CLI và các kết nối cần dùng. Áp dụng một lần, có backup. Không gọi model.</p>
<section><strong>1. Các agent</strong><div id="agents">Đang kiểm tra CLI và trạng thái đăng nhập…</div><p class="muted">Model mặc định: <strong>INHERIT</strong> cho tất cả. Giữ vai trò phù hợp; UNKNOWN không có nghĩa là đã đăng nhập hoặc còn quota.</p></section>
<section><strong>2. Kết nối</strong><div class="actions" id="actions"></div></section>
<div class="footer"><button id="apply" disabled>Áp dụng một lần</button><button id="refresh">Kiểm tra lại CLI</button></div><div role="status" aria-live="polite" id="status"></div>
<details><summary>Nâng cao</summary><p>Dùng <code>ma setup --advanced</code> để chọn model/role riêng, hoặc client MCP khác. Source, dữ liệu giả và API được xác nhận riêng tại <code>ma init</code> trong từng project.</p></details>
<script nonce="${nonce}">const api=acquireVsCodeApi();const box=document.getElementById('agents'),actions=document.getElementById('actions'),status=document.getElementById('status'),apply=document.getElementById('apply');
const labels={launcher:'Cài / cập nhật lệnh ma',chat:'Kết nối VS Code @hub',mcp:'Kết nối VS Code MCP'${windows ? ",wake:'Đánh thức hàng đợi tự động'" : ''}};
function makeCheck(name,text,checked,parent){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.dataset.name=name;input.checked=checked;label.append(input,document.createTextNode(' '+text));parent.append(label);return input;}
window.addEventListener('message',({data})=>{if(data.type==='plan'){box.replaceChildren();actions.replaceChildren();for(const agent of data.value.agents){const row=document.createElement('div');row.className='row';makeCheck(agent.agent,agent.agent,agent.enabled===true,row);const state=document.createElement('span');state.className='state';state.textContent=agent.state+' · '+(agent.authentication||'UNKNOWN');row.append(state);if(agent.state!=='NOT_INSTALLED'&&agent.authentication!=='AUTHENTICATED'){const login=document.createElement('button');login.textContent='Đăng nhập';login.addEventListener('click',()=>api.postMessage({type:'login',provider:agent.agent}));row.append(login);}box.append(row);}for(const [key,label] of Object.entries(labels))makeCheck(key,label,data.value.actions[key]===true,actions);apply.disabled=false;status.textContent='Chỉ các mục được tick mới được áp dụng.';}else if(data.type==='result'){status.textContent=data.message;apply.disabled=false;}else if(data.type==='busy'){status.textContent=data.message;apply.disabled=true;}});
apply.addEventListener('click',()=>{const providers=[...box.querySelectorAll('input:checked')].map(x=>x.dataset.name),selected={};for(const input of actions.querySelectorAll('input'))selected[input.dataset.name]=input.checked;api.postMessage({type:'apply',providers,actions:selected});});document.getElementById('refresh').addEventListener('click',()=>api.postMessage({type:'refresh'}));api.postMessage({type:'refresh'});</script></body></html>`;
}

function registerSetup(api, context, runtime, run) {
  context.subscriptions.push(api.commands.registerCommand('multi-agents.setup', () => {
    const panel = api.window.createWebviewPanel('multi-agents-setup', 'Multi Agents — Setup nhanh', api.ViewColumn.One,
      {enableScripts: true, localResourceRoots: []});
    panel.webview.html = setupHtml(randomBytes(18).toString('hex'), process.platform === 'win32');
    let busy = false;
    panel.webview.onDidReceiveMessage(async message => {
      if (busy) return;
      busy = true;
      try {
        if (message.type === 'refresh') {
          panel.webview.postMessage({type: 'busy', message: 'Đang kiểm tra CLI bằng lệnh chính thức; không gọi model…'});
          const value = JSON.parse(await run(['setup', '--plan', '--json']));
          panel.webview.postMessage({type: 'plan', value});
        } else if (message.type === 'apply') {
          panel.webview.postMessage({type: 'busy', message: 'Đang áp dụng các mục đã tick, giữ backup…'});
          const value = JSON.parse(await run(['setup', '--apply-options', JSON.stringify({providers: message.providers, actions: message.actions}), '--json']));
          panel.webview.postMessage({type: 'result', message: 'Setup xong. Model: INHERIT. Backup: ' + (value.backup || 'đã lưu') + '\nTiếp theo: vào project → ma init → @hub PROMPT.'});
        } else if (message.type === 'login') {
          if (!['codex', 'claude', 'copilot', 'antigravity'].includes(message.provider)) throw new Error('Invalid provider');
          const prefix = runtime.args.slice(0, runtime.args.indexOf('mcp'));
          const task = new api.Task({type: 'multi-agents-login'}, api.TaskScope.Global, 'Login ' + message.provider, 'Multi Agents',
            new api.ProcessExecution(runtime.command, [...prefix, 'setup', '--login', message.provider]));
          await api.tasks.executeTask(task);
          panel.webview.postMessage({type: 'result', message: 'Hoàn tất đăng nhập chính thức trong terminal vừa mở, rồi bấm Kiểm tra lại CLI. Không gửi token cho Hub.'});
        }
      } catch (error) { panel.webview.postMessage({type: 'result', message: 'Hub: ' + error.message}); }
      finally { busy = false; }
    }, undefined, context.subscriptions);
  }));
}
function registerSetupUri(api, context) {
  context.subscriptions.push(api.window.registerUriHandler({
    async handleUri(uri) {
      // Deep links can only open the UI; they cannot apply settings or pass commands.
      if (uri.scheme !== api.env.uriScheme || uri.authority !== 'khang1604.multi-agents-chat'
          || uri.path !== '/setup' || uri.query || uri.fragment) return;
      await api.commands.executeCommand('multi-agents.setup');
    }
  }));
}
module.exports = {registerSetup, registerSetupUri, setupHtml};
