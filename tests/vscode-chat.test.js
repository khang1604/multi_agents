'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {EventEmitter} = require('node:events');
const {PassThrough} = require('node:stream');
const {createHandler, summary} = require('../integrations/vscode-chat/handler');
const {Transport} = require('../integrations/vscode-chat/transport');
const {registerReview} = require('../integrations/vscode-chat/review');
const {registerSetup, registerSetupUri, setupHtml} = require('../integrations/vscode-chat/setup');

const project = {id: 'demo', name: 'Demo', path: path.resolve('synthetic-project')};
test('setup deep link opens only the interface, without accepting options or commands', async () => {
  let handler;
  const calls = [];
  registerSetupUri({env: {uriScheme: 'vscode'}, window: {registerUriHandler(value) { handler = value; return {}; }},
    commands: {async executeCommand(...args) { calls.push(args); }}}, {subscriptions: []});
  const valid = {scheme: 'vscode', authority: 'khang1604.multi-agents-chat', path: '/setup', query: '', fragment: ''};
  for (const invalid of [{path: '/apply'}, {query: 'apply=true'}, {fragment: 'login'}, {authority: 'other'}, {scheme: 'file'}]) {
    await handler.handleUri({...valid, ...invalid});
  }
  assert.deepEqual(calls, []);
  await handler.handleUri(valid);
  assert.deepEqual(calls, [['multi-agents.setup']]);
});
function api(trusted = true) {
  return {workspace: {isTrusted: trusted, workspaceFolders: [{uri: {scheme: 'file', fsPath: project.path}}]},
    window: {showQuickPick: async items => items[0]}};
}
function request(command, prompt = '') {
  return {command, prompt, get model() { throw new Error('MUST NOT ACCESS HOST MODEL'); }};
}
function fake(responses) {
  return {calls: [], disposed: false, async call(name, args) {
    this.calls.push({name, args});
    assert.ok(Object.hasOwn(responses, name), `Unexpected tool ${name}`);
    return typeof responses[name] === 'function' ? responses[name](args) : responses[name];
  }, dispose() { this.disposed = true; }};
}
const state = {id: 'f1', project_id: 'demo', status: 'completed', phase: 'review', calls: 3, max_calls: 6, daemon: 'running'};
function stream() { return {lines: [], markdown(line) { this.lines.push(line); }}; }

test('progress distinguishes the active worker from the elected leader', () => {
  const line = summary({...state, status: 'running', phase: 'implement', leader: 'copilot',
    current_agent: {provider: 'codex', role: 'implement'}});
  assert.match(line, /leader copilot/);
  assert.match(line, /implement: codex/);
});

test('agents uses stdio tools without touching quota-exhausted host model', async () => {
  const client = fake({list_agents: [{agent: 'codex', state: 'READY', authentication: 'UNKNOWN'}]});
  const out = stream();
  await createHandler(api(), async () => client)(request('agents'), {}, out, {});
  assert.match(out.lines.join(''), /codex CLI: READY/);
  assert.deepEqual(client.calls.map(c => c.name), ['list_agents']);
  assert.ok(client.disposed);
});

test('prompt dispatches once, retains Hub budget and streams final state', async () => {
  const client = fake({projects_list: [project], recover_context: {workflows: []},
    dispatch_task: state, get_workflow_status: state});
  const result = await createHandler(api(), async () => client)(request(undefined, 'Tạo tài liệu'), {}, stream(), {});
  const dispatch = client.calls.find(c => c.name === 'dispatch_task');
  assert.equal(dispatch.args.objective, 'Tạo tài liệu');
  assert.equal(dispatch.args.project, 'demo');
  assert.equal(dispatch.args.max_calls, undefined);
  assert.match(dispatch.args.request_key, /^[0-9a-f-]{36}$/);
  assert.equal(result.metadata.workflowId, 'f1');
});

test('daemon startup race keeps watching until the final answer without redispatch', async () => {
  let polls = 0;
  const client = fake({projects_list: [project], recover_context: {workflows: []}, dispatch_task: state,
    get_workflow_status: () => ++polls === 1 ? {...state, status: 'queued', daemon: 'stopped'} : state});
  const out = stream();
  await createHandler(api(), async () => client, async () => {})(request(undefined, 'Synthetic task'), {}, out, {});
  assert.equal(polls, 2);
  assert.match(out.lines.join(''), /completed/);
  assert.equal(client.calls.filter(c => c.name === 'dispatch_task').length, 1);
});

test('stopped daemon grace is bounded and disabled providers show OFF', async () => {
  const stopped = fake({projects_list: [project], recover_context: {workflows: [state]},
    get_workflow_status: {...state, status: 'queued', daemon: 'stopped'}});
  await createHandler(api(), async () => stopped, async () => {})(request('watch'), {}, stream(), {});
  assert.equal(stopped.calls.filter(c => c.name === 'get_workflow_status').length, 6);
  const client = fake({list_agents: [{agent: 'claude', enabled: false, state: 'INSTALLED'}]});
  const out = stream();
  await createHandler(api(), async () => client)(request('agents'), {}, out, {});
  assert.match(out.lines.join(''), /OFF/);
});

test('active workflow prevents duplicate prompt dispatch', async () => {
  const client = fake({projects_list: [project], recover_context: {workflows: [{...state, status: 'waiting'}]}});
  await createHandler(api(), async () => client)(request(undefined, 'another task'), {}, stream(), {});
  assert.ok(!client.calls.some(c => c.name === 'dispatch_task'));
});

test('untrusted/unregistered workspace cannot dispatch', async () => {
  let connected = false;
  await createHandler(api(false), async () => { connected = true; })(request(undefined, 'task'), {}, stream(), {});
  assert.equal(connected, false);
  const client = fake({projects_list: []});
  await createHandler(api(), async () => client)(request(undefined, 'task'), {}, stream(), {});
  assert.ok(!client.calls.some(c => c.name === 'dispatch_task'));
});

test('retry preserves budget; cross-project cancel is refused', async () => {
  const client = fake({projects_list: [project], recover_context: {workflows: [{...state, status: 'blocked'}]},
    workflow_retry: state, get_workflow_status: state});
  await createHandler(api(), async () => client)(request('retry'), {}, stream(), {});
  assert.deepEqual(client.calls.find(c => c.name === 'workflow_retry').args, {workflow_id: 'f1'});
  const other = fake({projects_list: [project], recover_context: {workflows: []},
    workflow_status: {...state, project_id: 'other-project'}});
  await createHandler(api(), async () => other)(request('cancel', 'other'), {}, stream(), {});
  assert.ok(!other.calls.some(c => c.name === 'cancel_workflow'));
});

test('stopping chat monitor does not cancel workflow; waiting stops polling', async () => {
  const client = fake({projects_list: [project], recover_context: {workflows: [state]},
    get_workflow_status: {...state, status: 'waiting', next_run: 1234567890}});
  await createHandler(api(), async () => client)(request('watch'), {}, stream(), {});
  assert.equal(client.calls.filter(c => c.name === 'get_workflow_status').length, 1);
  assert.ok(!client.calls.some(c => c.name === 'cancel_workflow'));
  assert.ok(client.disposed);
});

test('untrusted provider text cannot create command/HTML links', async () => {
  const client = fake({list_agents: [{agent: 'x', state: 'UNKNOWN', reason: '[click](command:evil)<img src=x>'}]});
  const out = stream();
  await createHandler(api(), async () => client)(request('agents'), {}, out, {});
  assert.ok(out.lines[0].includes('\\[click\\]\\(command:evil\\)\\<img'));
});

test('transport handles chunked replies and rejects pending calls on exit', async () => {
  const child = new EventEmitter();
  child.stdin = new PassThrough(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
  child.exitCode = null; child.kill = () => { child.exitCode = 0; };
  let options;
  const transport = new Transport({command: 'pinned-python', args: ['ma.py', 'mcp']}, (cmd, args, opts) => { options = opts; return child; });
  const response = transport.request('ping');
  child.stdout.write('{"jsonrpc":"2.0","id":1,');
  child.stdout.write('"result":{}}\n');
  assert.deepEqual(await response, {});
  assert.equal(options.shell, false);
  assert.equal(options.env.PYTHONIOENCODING, 'utf-8');
  assert.equal(options.env.PYTHONUTF8, '1');
  const pending = transport.request('ping');
  child.emit('exit', 1);
  await assert.rejects(pending, /đã đóng/);
  transport.dispose();
});

test('blocked budget renders persisted answer, review and file without new dispatch', async () => {
  const blocked = {...state, status: 'blocked', calls: 6, max_calls: 6,
    reports: [{summary: 'Đã rà soát tính năng', findings: ['Quiz thiếu chấm điểm']}],
    reviews: [{verdict: 'changes_requested', findings: ['Cập nhật bằng chứng test']}],
    checks: [{exit_code: 0}], workspace: project.path, changed_files: ['FEATURES_AUDIT.md', '../private.txt']};
  const client = fake({projects_list: [project], recover_context: {workflows: [blocked]}, get_workflow_status: blocked});
  const out = stream();
  await createHandler(api(), async () => client)(request('status'), {}, out, {});
  const text = out.lines.join('');
  assert.match(text, /Quiz thiếu chấm điểm/);
  assert.match(text, /Cập nhật bằng chứng test/);
  assert.match(text, /ngân sách/);
  assert.match(text, /FEATURES/);
  assert.ok(!text.includes('private.txt'));
  assert.ok(!client.calls.some(c => ['dispatch_task','workflow_retry'].includes(c.name)));
});

test('completed output distinguishes final verification from historical worker errors', async () => {
  const completed = {...state, summary: 'Implementation accepted after independent checks',
    reports: [{summary: 'Worker Python unavailable', findings: ['Worker could not run tests']}],
    reviews: [{provider: 'copilot', verdict: 'approve'}], checks: [{exit_code: 0}]};
  const client = fake({projects_list: [project], recover_context: {workflows: [completed]}, get_workflow_status: completed});
  const out = stream();
  await createHandler(api(), async () => client)(request('status'), {}, out, {});
  const text = out.lines.join('');
  assert.match(text, /Kết luận sau kiểm tra/);
  assert.match(text, /Ghi chú worker trước verifier/);
  assert.match(text, /Verifier: PASS/);
  assert.match(text, /Review copilot: approve/);
});

test('Copilot agent availability is labelled CLI, independent of Chat', async () => {
  const client = fake({list_agents: [{agent: 'copilot', state: 'NOT_INSTALLED'}]});
  const out = stream();
  await createHandler(api(), async () => client)(request('agents'), {}, out, {});
  assert.match(out.lines.join(''), /copilot CLI/);
  assert.match(out.lines.join(''), /Copilot Chat vẫn dùng được/);
});

test('real stdio Hub can serve agents to handler with no model calls', {skip: !process.env.HUB_TEST_HOME}, async () => {
  const connect = async () => {
    const client = new Transport({command: process.env.HUB_TEST_PYTHON,
      args: [path.resolve(__dirname, '../ma.py'), '--home', process.env.HUB_TEST_HOME, 'mcp', '--client', 'test-chat']});
    await client.initialize(); return client;
  };
  const out = stream();
  await createHandler(api(), connect)(request('agents'), {}, out, {});
  assert.equal(out.lines.length, 4);
  assert.match(out.lines.join(''), /codex/);
});


test('accept requires human modal confirmation before applying files', async () => {
  for (const decision of [undefined, 'Accept']) {
    const ui = api();
    ui.window.showWarningMessage = async () => decision;
    const client = fake({projects_list: [project], recover_context: {workflows: [state]}});
    const applied = [];
    await createHandler(ui, async () => client, undefined, async (...args) => {
      applied.push(args); return 'accepted';
    })(request('accept'), {}, stream(), {});
    assert.equal(applied.length, decision === 'Accept' ? 1 : 0);
    if (applied.length) assert.deepEqual(applied[0], [['accept', 'f1', '--json'], project.path]);
  }
});

test('auto accept enable requires confirmation and only targets current project', async () => {
  for (const decision of [undefined, 'Bật Auto accept']) {
    const ui = api();
    ui.window.showWarningMessage = async () => decision;
    const client = fake({projects_list: [project]});
    const applied = [];
    await createHandler(ui, async () => client, undefined, async (...args) => {
      applied.push(args); return 'enabled';
    })(request('autoaccept', 'on'), {}, stream(), {});
    assert.equal(applied.length, decision ? 1 : 0);
    if (applied.length) assert.deepEqual(applied[0], [['auto-accept', 'on', '--json'], project.path]);
  }
});

function reviewUI(value) {
  const ui = api(), commands = new Map(), executed = [], errors = [], calls = [];
  let provider;
  ui.Uri = {from: parts => ({...parts, toString() { return parts.scheme + ':' + parts.path + '?' + parts.query; }})};
  ui.workspace.registerTextDocumentContentProvider = (scheme, p) => { assert.equal(scheme, 'ma-review'); provider = p; return {dispose() {}}; };
  ui.commands = {registerCommand(id, fn) { commands.set(id, fn); return {dispose() {}}; },
    async executeCommand(...args) { executed.push(args); }};
  ui.window.showWarningMessage = async () => undefined;
  ui.window.showInformationMessage = () => {};
  ui.window.showErrorMessage = error => errors.push(error);
  const connect = async () => fake({projects_list: [project]});
  const run = async (args, cwd) => { calls.push({args, cwd}); return JSON.stringify(args[0] === 'review' ? value : {status: 'partial', remaining_files: ['other.py']}); };
  registerReview(ui, {subscriptions: []}, connect, run);
  return {ui, commands, executed, errors, calls, get provider() { return provider; }};
}
const preview = {workflow_id: 'f1', project_id: 'demo', project_path: project.path, acceptance: {status: 'pending'},
  files: [{path: 'app/code.py', before: 'old code', after: 'new code', kind: 'modified', accepted: false}]};

test('native diff uses readonly virtual content; accepting needs explicit confirmation', async () => {
  const env = reviewUI(preview);
  await env.commands.get('multi-agents.review')({workflowId: 'f1'});
  assert.equal(env.executed[0][0], 'vscode.diff');
  assert.equal(env.provider.provideTextDocumentContent(env.executed[0][1]), 'old code');
  assert.equal(env.provider.provideTextDocumentContent(env.executed[0][2]), 'new code');
  await env.commands.get('multi-agents.acceptFile')({workflowId: 'f1'});
  assert.equal(env.calls.filter(c => c.args[0] === 'accept').length, 0);
  env.ui.window.showWarningMessage = async () => 'Accept file';
  await env.commands.get('multi-agents.acceptFile')({workflowId: 'f1'});
  assert.deepEqual(env.calls.at(-1).args, ['accept', 'f1', '--project', 'demo', '--json', '--file', 'app/code.py']);
});

test('native review refuses other projects and unsafe file references', async () => {
  for (const value of [{...preview, project_id: 'other'}, {...preview, files: [{...preview.files[0], path: '../private'}]}]) {
    const env = reviewUI(value);
    await env.commands.get('multi-agents.review')({workflowId: 'f1'});
    assert.equal(env.executed.length, 0);
    assert.equal(env.errors.length, 1);
  }
  const env = reviewUI(preview);
  env.ui.workspace.isTrusted = false;
  await env.commands.get('multi-agents.acceptAll')({workflowId: 'f1'});
  assert.equal(env.calls.length, 0);
});

test('completed chat offers review and accept buttons; blocked has none', async () => {
  for (const status of ['completed', 'blocked']) {
    const buttons = [], out = stream(); out.button = value => buttons.push(value);
    const current = {...state, status};
    const client = fake({projects_list: [project], recover_context: {workflows: [current]}, get_workflow_status: current});
    await createHandler(api(), async () => client)(request('status'), {}, out, {});
    assert.deepEqual(buttons.map(b => b.command), status === 'completed'
      ? ['multi-agents.review', 'multi-agents.acceptAll', 'multi-agents.acceptFile'] : []);
  }
});

test('setup webview uses nonce CSP, no remote resources, one apply command and official login process task', async () => {
  const html = setupHtml('testnonce', true);
  assert.match(html, /default-src 'none'/);
  assert.match(html, /script-src 'nonce-testnonce'/);
  assert.ok(!html.includes('https://'));
  const ui = api(), commands = new Map(), calls = [], tasks = [];
  let receive;
  ui.ViewColumn = {One: 1}; ui.TaskScope = {Global: 1};
  ui.ProcessExecution = class { constructor(command, args) { this.command = command; this.args = args; } };
  ui.Task = class { constructor(definition, scope, name, source, execution) { this.execution = execution; } };
  ui.tasks = {async executeTask(task) { tasks.push(task); }};
  ui.commands = {registerCommand(id, fn) { commands.set(id, fn); return {dispose() {}}; }};
  const messages = [];
  ui.window.createWebviewPanel = (id, title, column, options) => {
    assert.deepEqual(options.localResourceRoots, []);
    return {webview: {postMessage: message => messages.push(message), onDidReceiveMessage(fn) { receive = fn; }}};
  };
  registerSetup(ui, {subscriptions: []}, {command: 'pinned-python', args: ['ma.py', '--home', 'owned-home', 'mcp']},
    async args => { calls.push(args); return JSON.stringify(args.includes('--plan') ? {agents: [], actions: {}} : {backup: 'owned-backup'}); });
  commands.get('multi-agents.setup')();
  await receive({type: 'refresh'});
  await receive({type: 'apply', providers: ['codex'], actions: {chat: false}});
  assert.equal(calls.filter(c => c.includes('--apply-options')).length, 1);
  assert.deepEqual(JSON.parse(calls[1][2]), {providers: ['codex'], actions: {chat: false}});
  await receive({type: 'login', provider: 'codex'});
  assert.deepEqual(tasks[0].execution.args, ['ma.py', '--home', 'owned-home', 'setup', '--login', 'codex']);
  assert.equal(calls.some(c => c.includes('--login')), false);
});
