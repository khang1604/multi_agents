'use strict';
const path = require('node:path');
const {randomUUID} = require('node:crypto');
const {selectProject} = require('./handler');

function registerReview(api, context, connect, run) {
  const texts = new Map();
  let viewed;
  context.subscriptions.push(api.workspace.registerTextDocumentContentProvider('ma-review', {
    provideTextDocumentContent(uri) {
      if (!texts.has(uri.toString())) throw new Error('Preview expired; open changes again.');
      return texts.get(uri.toString());
    }
  }));
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
  async function choose(value, remaining = false) {
    return api.window.showQuickPick(value.files.filter(f => !remaining || !f.accepted).map(file => ({
      label: file.path, description: file.accepted ? 'Đã Accept' : file.kind, file
    })), {placeHolder: remaining ? 'Chọn file muốn Accept' : 'Chọn file để xem diff: bản cũ bên trái, bản mới bên phải'});
  }
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
      if (loaded.value.acceptance.status === 'accepted') { api.window.showInformationMessage('Các thay đổi đã được Accept.'); return; }
      const title = single ? 'Accept file' : 'Accept tất cả';
      const message = single ? 'Áp dụng ' + file.path + ' vào project?' : 'Áp dụng tất cả file còn lại của ' + args.workflowId + '?';
      if (await api.window.showWarningMessage(message, {modal: true}, title) !== title) return;
      const command = ['accept', args.workflowId, '--project', loaded.project.id, '--json'];
      if (single) command.push('--file', file.path);
      const result = JSON.parse(await run(command, loaded.project.path));
      api.window.showInformationMessage(result.status === 'accepted' ? 'Đã Accept tất cả thay đổi.'
        : 'Đã Accept file. Còn ' + result.remaining_files.length + ' file chưa áp dụng; project có thể cần các file đó để chạy.');
    });
  }
}
module.exports = {registerReview};
