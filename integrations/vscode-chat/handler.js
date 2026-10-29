'use strict';
const path = require('node:path');
const {randomUUID} = require('node:crypto');
const terminal = new Set(['completed', 'blocked', 'cancelled', 'needs_review']);
/** Sanitize and bound untrusted provider text before displaying it. */
function clean(value, length = 360) {
  return String(value || '').replace(/[\r\n\x00-\x1f\x7f]/g, ' ').slice(0, length);
}
/** Write escaped untrusted text to the chat stream without trusted command links. */
function plain(stream, value) {
  // A MarkdownString with no trust, HTML or command links; escape provider output.
  stream.markdown(clean(value, 1800).replace(/[\\`*_{}\[\]()<>!#|]/g, '\\$&') + '\n\n');
}
/** Summarize actual workflow phase, provider, budget, and acceptance state. */
function summary(state) {
  let line = `${state.id}: ${state.status}/${state.phase} · leader ${state.leader || '?'} · ${state.calls}/${state.max_calls} calls`;
  if (state.current_agent) line += ` · ${clean(state.current_agent.role, 30)}: ${clean(state.current_agent.provider, 40)}`;
  if (state.next_run && state.status === 'waiting') line += ` · retry ${new Date(state.next_run * 1000).toLocaleString()}`;
  if (state.error) line += ` · ${clean(state.error)}`;
  if (state.status === 'completed') line += state.acceptance?.status === 'accepted' ? ' · Applied to files' : ' · Awaiting acceptance: /accept';
  return line;
}
/** Render saved reports, verifier evidence, and permitted review/accept controls. */
function outcome(stream, state) {
  if (!terminal.has(state.status)) return;
  plain(stream, state.status === 'completed' ? 'Results:' : 'Partial results saved; workflow is not complete:');
  if (state.status === 'completed' && state.summary) plain(stream, 'Conclusion after verification/review: ' + state.summary);
  const seen = new Set();
  for (const report of (state.reports || []).slice(0, 2)) {
    if (report.summary) plain(stream, (state.status === 'completed' ? 'Worker report before verification: ' : '') + report.summary);
    for (const finding of (report.findings || []).slice(0, 5)) {
      if (!seen.has(finding)) { plain(stream, (state.status === 'completed' ? 'Worker notes before verification: ' : '• ') + finding); seen.add(finding); }
    }
  }
  if (!(state.reports || []).length) plain(stream, state.summary || 'No implementation report yet.');
  for (const review of (state.reviews || []).slice(0, 2)) {
    if (review.verdict === 'approve') plain(stream, `Review ${review.provider || ''}: approve.`);
    if (review.verdict === 'changes_requested') {
      for (const finding of (review.findings || []).slice(0, 3)) plain(stream, 'Changes requested: ' + finding);
    }
  }
  const checks = state.checks || [];
  if (checks.length) plain(stream, `Verifier: ${checks.every(c => c.exit_code === 0) ? 'PASS' : 'FAIL'} (results saved; does not replace review/UI testing).`);
  for (const file of (state.changed_files || []).slice(0, 3)) {
    if (state.workspace && typeof file === 'string' && !path.isAbsolute(file) && within(state.workspace, path.resolve(state.workspace, file)))
      plain(stream, 'File in worktree: ' + path.join(state.workspace, file));
  }
  if (state.status === 'completed' && typeof stream.button === 'function') {
    const args = [{workflowId: state.id}];
    stream.button({command: 'multi-agents.review', title: 'Review changes', arguments: args});
    if (state.acceptance?.status !== 'accepted') {
      stream.button({command: 'multi-agents.acceptAll', title: 'Accept all', arguments: args});
      stream.button({command: 'multi-agents.acceptFile', title: 'Accept individual files', arguments: args});
    }
  }
  if (state.status === 'blocked' && state.calls >= state.max_calls)
    plain(stream, 'AI call budget exhausted; /retry does not grant more calls. Results and checkpoints are retained.');
}
/** Check that a resolved path stays within the selected project root. */
function within(root, folder) {
  const relative = path.relative(path.resolve(root), path.resolve(folder));
  return relative === '' || (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative));
}
/** Match the open trusted workspace to an approved registered Hub project. */
async function selectProject(api, client) {
  const folders = api.workspace.workspaceFolders || [];
  const projects = await client.call('projects_list');
  const matching = projects.filter(p => folders.some(f => f.uri.scheme === 'file' && within(p.path, f.uri.fsPath)));
  if (!matching.length) throw new Error('Open the approved project and run ma init once in that project.');
  if (matching.length === 1) return matching[0];
  const selected = await api.window.showQuickPick(matching.map(p => ({label: p.name, description: p.path, project: p})),
    {placeHolder: 'Select the project for this prompt'});
  return selected && selected.project;
}
/** Create a chat handler that dispatches and monitors Hub work without using the host model. */
function createHandler(api, connect, wait = ms => new Promise(resolve => setTimeout(resolve, ms)), applyChanges) {
  // No workspace source reads, chat history forwarding, model API or recursive dispatch.
  return async (request, context, stream, token) => {
    let client;
    let workflow;
    try {
      if (!api.workspace.isTrusted) throw new Error('Trust the workspace before connecting to Hub.');
      if (token.isCancellationRequested) return {};
      client = await connect();
      if (request.command === 'agents') {
        const rows = await client.call('list_agents');
        for (const row of rows) plain(stream, `${row.agent} CLI: ${row.state} · ${row.enabled === false ? 'OFF · Disabled in configuration' : (row.agent === 'copilot' && row.state === 'NOT_INSTALLED' ? 'CLI not installed; Copilot Chat is still available' : (row.reason || (row.operator_confirmed ? 'Operator confirmed AI use' : row.authentication)))}`);
        return {};
      }
      const project = await selectProject(api, client);
      if (!project || token.isCancellationRequested) return {};
      if (request.command === 'autoaccept') {
        const choice = request.prompt.trim() || 'status';
        if (!['on', 'off', 'status'].includes(choice)) throw new Error('Use /autoaccept on, off or status.');
        if (!applyChanges) throw new Error('Update the extension to use Accept.');
        if (choice === 'on' && await api.window.showWarningMessage(
          'Automatically apply verified code to files in this project? Hub still stops if there are conflicting changes.',
          {modal: true}, 'Enable Auto accept') !== 'Enable Auto accept') return {};
        plain(stream, await applyChanges(['auto-accept', choice, '--json'], project.path));
        return {};
      }
      const recovered = await client.call('recover_context', {project: project.id});
      const flows = recovered.workflows || [];
      if (request.command) {
        workflow = flows[0];
        // Restrict an explicit id to this workspace, including older workflows via status check.
        const id = request.prompt.trim();
        if (id) {
          const state = await client.call('workflow_status', {workflow_id: id, include_details: true});
          if (state.project_id !== project.id) throw new Error('Workflow belongs to another project.');
          workflow = state;
        }
        if (!workflow) { plain(stream, 'This project has no workflow yet. Enter @hub and the work you want done.'); return {}; }
        if (token.isCancellationRequested) return {};
        if (request.command === 'accept') {
          if (!applyChanges) throw new Error('Update the extension to use Accept.');
          if (await api.window.showWarningMessage('Apply changes from ' + workflow.id + ' to project files?',
            {modal: true}, 'Accept') !== 'Accept') return {};
          plain(stream, await applyChanges(['accept', workflow.id, '--json'], project.path));
          return {metadata: {workflowId: workflow.id}};
        }
        if (request.command === 'cancel') {
          await client.call('cancel_workflow', {workflow_id: workflow.id});
          plain(stream, `Cancellation requested for ${workflow.id}; code/checkpoints retained.`);
          return {metadata: {workflowId: workflow.id}};
        }
        if (request.command === 'retry') {
          // extra_calls is deliberately absent: a retry never silently grants more budget.
          workflow = await client.call('workflow_retry', {workflow_id: workflow.id});
        } else if (!['status', 'watch'].includes(request.command)) {
          throw new Error('Unsupported command. Use /agents, /status, /watch, /retry or /cancel.');
        }
      } else {
        const active = flows.find(flow => !terminal.has(flow.status));
        if (active) {
          plain(stream, summary(active));
          plain(stream, 'A workflow is already active; use @hub /watch or /cancel. The new prompt has not been submitted.');
          return {metadata: {workflowId: active.id}};
        }
        const objective = request.prompt.trim();
        if (!objective) { plain(stream, 'Enter @hub and your task. Check progress with @hub /status.'); return {}; }
        if (objective.length > 12000) throw new Error('Prompt is too long; shorten it to at most 12,000 characters.');
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
          if (terminal.has(workflow.status) || workflow.status === 'waiting') break;
          // A newly spawned daemon may not own its lock on the first read.
          // Allow a bounded startup grace period instead of dropping the answer.
          if (workflow.daemon === 'stopped' && count >= 5) break;
          await wait(2000);
        }
        if (!terminal.has(workflow.status)) plain(stream, 'Checkpoint saved. Use @hub /watch to continue watching; /cancel to stop the task.');
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
