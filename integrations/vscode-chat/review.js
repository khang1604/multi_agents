'use strict';
const path = require('node:path');
const {randomUUID} = require('node:crypto');
const {selectProject} = require('./handler');

/** Register read-only delivery previews and explicit acceptance commands. */
function registerReview(api, context, connect, run) {
  const texts = new Map();
  let viewed;
  context.subscriptions.push(api.workspace.registerTextDocumentContentProvider('ma-review', {
    provideTextDocumentContent(uri) {
      if (!texts.has(uri.toString())) throw new Error('Preview expired; open changes again.');
      return texts.get(uri.toString());
    }
  }));
  /** Load verified review data for the selected project and reject unsafe file paths. */
  async function load(args) {
    if (!api.workspace.isTrusted) throw new Error('Trust workspace before reviewing changes.');
    if (!args || typeof args.workflowId !== 'string' || !/^[a-zA-Z0-9_-]{1,80}$/.test(args.workflowId))
      throw new Error('Invalid workflow.');
    const client = await connect();
    let project;
    try { project = await selectProject(api, client); } finally { client.dispose(); }
    if (!project) return;
    const value = JSON.parse(await run(['review', args.workflowId, '--project', project.id, '--json'], project.path));
    if (value.project_id !== project.id || value.workflow_id !== args.workflowId || path.resolve(value.project_path) !== path.resolve(project.path))
      throw new Error('Review belongs to another project.');
    if (!Array.isArray(value.files) || value.files.some(f => !f.path || path.isAbsolute(f.path) || /[:\\]/.test(f.path) || f.path.split('/').includes('..') || typeof f.before !== 'string' || typeof f.after !== 'string'))
      throw new Error('Invalid preview files.');
    return {project, value};
  }
  /** Let the operator choose a delivery file for review or acceptance. */
  async function choose(value, remaining = false) {
    return api.window.showQuickPick(value.files.filter(f => !remaining || !f.accepted).map(file => ({
      label: file.path, description: file.accepted ? 'Accepted' : file.kind, file
    })), {placeHolder: remaining ? 'Select a file to accept' : 'Select a file to view its diff: original on the left, updated on the right'});
  }
  /** Register a UI command with bounded error reporting. */
  function command(id, fn) {
    context.subscriptions.push(api.commands.registerCommand(id, async args => {
      try { return await fn(args); }
      catch (error) { api.window.showErrorMessage('Hub: ' + error.message); }
    }));
  }
  command('multi-agents.review', async args => {
    const loaded = await load(args); if (!loaded) return;
    const picked = await choose(loaded.value); if (!picked) return;
    const file = picked.file;
    const nonce = randomUUID();
    const before = api.Uri.from({scheme: 'ma-review', path: '/' + nonce + '/' + file.path, query: 'before'});
    const after = api.Uri.from({scheme: 'ma-review', path: '/' + nonce + '/' + file.path, query: 'after'});
    texts.set(before.toString(), file.before); texts.set(after.toString(), file.after);
    while (texts.size > 64) texts.delete(texts.keys().next().value);
    viewed = {workflowId: args.workflowId, projectId: loaded.project.id, path: file.path};
    await api.commands.executeCommand('vscode.diff', before, after, file.path + ' — Multi Agents (' + file.kind + ')');
  });
  for (const [id, single] of [['multi-agents.acceptAll', false], ['multi-agents.acceptFile', true]]) {
    command(id, async args => {
      const loaded = await load(args); if (!loaded) return;
      let file;
      if (single) {
        file = viewed?.workflowId === args.workflowId && viewed.projectId === loaded.project.id
          ? loaded.value.files.find(f => f.path === viewed.path && !f.accepted) : undefined;
        if (!file) file = (await choose(loaded.value, true))?.file;
        if (!file) return;
      }
      if (loaded.value.acceptance.status === 'accepted') { api.window.showInformationMessage('Changes have already been accepted.'); return; }
      const title = single ? 'Accept file' : 'Accept all';
      const message = single ? 'Apply ' + file.path + ' to the project?' : 'Apply all remaining files from ' + args.workflowId + '?';
      if (await api.window.showWarningMessage(message, {modal: true}, title) !== title) return;
      const command = ['accept', args.workflowId, '--project', loaded.project.id, '--json'];
      if (single) command.push('--file', file.path);
      const result = JSON.parse(await run(command, loaded.project.path));
      api.window.showInformationMessage(result.status === 'accepted' ? 'All changes accepted.'
        : 'File accepted. There are ' + result.remaining_files.length + ' files still unapplied; the project may need them to run.');
    });
  }
}
module.exports = {registerReview};
