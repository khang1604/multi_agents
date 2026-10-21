'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {EventEmitter} = require('node:events');
const {PassThrough} = require('node:stream');
const {createHandler, summary} = require('../integrations/vscode-chat/handler');
const {Transport} = require('../integrations/vscode-chat/transport');

const project = {id: 'demo', name: 'Demo', path: path.resolve('synthetic-project')};
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
