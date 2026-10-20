'use strict';
const path = require('node:path');
const {randomUUID} = require('node:crypto');
const terminal = new Set(['completed', 'blocked', 'cancelled', 'needs_review']);
function clean(value, length = 360) {
  return String(value || '').replace(/[\r\n\x00-\x1f\x7f]/g, ' ').slice(0, length);
}
function plain(stream, value) {
  // A MarkdownString with no trust, HTML or command links; escape provider output.
  stream.markdown(clean(value, 1800).replace(/[\\`*_{}\[\]()<>!#|]/g, '\\$&') + '\n\n');
}
function summary(state) {
  let line = `${state.id}: ${state.status}/${state.phase} · leader ${state.leader || '?'} · ${state.calls}/${state.max_calls} calls`;
  if (state.next_run && state.status === 'waiting') line += ` · thử lại ${new Date(state.next_run * 1000).toLocaleString()}`;
  if (state.error) line += ` · ${clean(state.error)}`;
  if (state.delivery) line += ` · ZIP: ${clean(state.delivery)}`;
  return line;
}
function outcome(stream, state) {
  if (!terminal.has(state.status)) return;
  plain(stream, state.status === 'completed' ? 'Kết quả:' : 'Kết quả tạm đã lưu; workflow chưa hoàn tất:');
  const seen = new Set();
  for (const report of (state.reports || []).slice(0, 2)) {
    if (report.summary) plain(stream, report.summary);
    for (const finding of (report.findings || []).slice(0, 5)) {
      if (!seen.has(finding)) { plain(stream, '• ' + finding); seen.add(finding); }
    }
  }
  if (!(state.reports || []).length) plain(stream, state.summary || 'Chưa có báo cáo thực hiện.');
  for (const review of (state.reviews || []).slice(0, 2)) {
    if (review.verdict === 'changes_requested') {
      for (const finding of (review.findings || []).slice(0, 3)) plain(stream, 'Cần sửa: ' + finding);
    }
  }
  const checks = state.checks || [];
  if (checks.length) plain(stream, `Verifier: ${checks.every(c => c.exit_code === 0) ? 'PASS' : 'FAIL'} (kết quả đã lưu; không thay thế review/UI test).`);
  for (const file of (state.changed_files || []).slice(0, 3)) {
    if (state.workspace && typeof file === 'string' && !path.isAbsolute(file) && within(state.workspace, path.resolve(state.workspace, file)))
      plain(stream, 'File trong worktree: ' + path.join(state.workspace, file));
  }
  if (state.status === 'blocked' && state.calls >= state.max_calls)
    plain(stream, 'Đã hết ngân sách lượt AI; /retry không cấp thêm lượt. Kết quả và checkpoint vẫn được giữ.');
}
function within(root, folder) {
  const relative = path.relative(path.resolve(root), path.resolve(folder));
  return relative === '' || (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative));
}
async function selectProject(api, client) {
  const folders = api.workspace.workspaceFolders || [];
  const projects = await client.call('projects_list');
  const matching = projects.filter(p => folders.some(f => f.uri.scheme === 'file' && within(p.path, f.uri.fsPath)));
  if (!matching.length) throw new Error('Mở đúng project đã cho phép, chạy ma init một lần trong project đó.');
  if (matching.length === 1) return matching[0];
  const selected = await api.window.showQuickPick(matching.map(p => ({label: p.name, description: p.path, project: p})),
    {placeHolder: 'Chọn project cho prompt này'});
  return selected && selected.project;
}
function createHandler(api, connect, wait = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  // No workspace source reads, chat history forwarding, model API or recursive dispatch.
  return async (request, context, stream, token) => {
    let client;
    let workflow;
    try {
      if (!api.workspace.isTrusted) throw new Error('Cần Trust workspace trước khi kết nối Hub.');
      if (token.isCancellationRequested) return {};
      client = await connect();
      if (request.command === 'agents') {
        const rows = await client.call('list_agents');
        for (const row of rows) plain(stream, `${row.agent} CLI: ${row.state} · ${row.agent === 'copilot' && row.state === 'NOT_INSTALLED' ? 'Chưa cài CLI; Copilot Chat vẫn dùng được' : (row.reason || (row.operator_confirmed ? 'Bạn xác nhận chạy AI' : row.authentication))}`);
        return {};
      }
      const project = await selectProject(api, client);
      if (!project || token.isCancellationRequested) return {};
      const recovered = await client.call('recover_context', {project: project.id});
      const flows = recovered.workflows || [];
      if (request.command) {
        workflow = flows[0];
        // Restrict an explicit id to this workspace, including older workflows via status check.
        const id = request.prompt.trim();
        if (id) {
          const state = await client.call('workflow_status', {workflow_id: id, include_details: true});
          if (state.project_id !== project.id) throw new Error('Workflow thuộc project khác.');
          workflow = state;
        }
        if (!workflow) { plain(stream, 'Project chưa có workflow. Nhập @hub và công việc bạn muốn làm.'); return {}; }
        if (token.isCancellationRequested) return {};
        if (request.command === 'cancel') {
          await client.call('cancel_workflow', {workflow_id: workflow.id});
          plain(stream, `Đã yêu cầu dừng ${workflow.id}; giữ code/checkpoint.`);
          return {metadata: {workflowId: workflow.id}};
        }
        if (request.command === 'retry') {
          // extra_calls is deliberately absent: a retry never silently grants more budget.
          workflow = await client.call('workflow_retry', {workflow_id: workflow.id});
        } else if (!['status', 'watch'].includes(request.command)) {
          throw new Error('Lệnh chưa hỗ trợ. Dùng /agents, /status, /watch, /retry hoặc /cancel.');
        }
      } else {
        const active = flows.find(flow => !terminal.has(flow.status));
        if (active) {
          plain(stream, summary(active));
          plain(stream, 'Đang có workflow; dùng @hub /watch hoặc /cancel. Prompt mới chưa được gửi.');
          return {metadata: {workflowId: active.id}};
        }
        const objective = request.prompt.trim();
        if (!objective) { plain(stream, 'Nhập @hub và công việc. Xem trạng thái bằng @hub /status.'); return {}; }
        if (objective.length > 12000) throw new Error('Prompt quá dài; rút xuống tối đa 12.000 ký tự.');
        if (token.isCancellationRequested) return {};
        workflow = await client.call('dispatch_task', {project: project.id, objective, request_key: randomUUID()});
      }
      if (request.command === 'status') {
        workflow = await client.call('get_workflow_status', {workflow_id: workflow.id});
        plain(stream, summary(workflow));
      } else {
        let previous = '';
        // Bound one chat view to ten minutes. Daemon/checkpoint continue independently.
        for (let count = 0; count < 300 && !token.isCancellationRequested; count++) {
          workflow = await client.call('get_workflow_status', {workflow_id: workflow.id});
          const line = summary(workflow);
          if (line !== previous) { plain(stream, line); previous = line; }
          if (terminal.has(workflow.status) || workflow.status === 'waiting' || workflow.daemon === 'stopped') break;
          await wait(2000);
        }
        if (!terminal.has(workflow.status)) plain(stream, 'Checkpoint đã lưu. Dùng @hub /watch để xem tiếp; /cancel để dừng task.');
      }
      outcome(stream, workflow);
      return {metadata: {workflowId: workflow.id}};
    } catch (error) {
      plain(stream, `Hub: ${clean(error.message, 900)}`);
      return workflow ? {metadata: {workflowId: workflow.id}} : {};
    } finally {
      if (client) client.dispose();
    }
  };
}
module.exports = {createHandler, selectProject, summary, within};
