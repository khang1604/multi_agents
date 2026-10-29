"""MCP stdio transport. stdout is reserved for JSON-RPC replies."""
import json
import os
import sys
from .api import Hub


def tool(name, description, props, required):
    """Build a strict MCP tool definition and argument schema."""
    return {'name': name, 'description': description, 'inputSchema': {
        'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}}


STR = {'type': 'string'}
TOOLS = [
    tool('projects_list', 'List registered local projects; no AI call.', {}, []),
    tool('workflow_start', 'Create an Auto workflow. Durable, isolated worktree, bounded AI calls. request_key deduplicates retries.',
         {'project': STR, 'objective': STR, 'request_key': STR, 'max_calls': {'type': 'integer', 'minimum': 1, 'maximum': 50},
          'handoff': {'type':'object', 'properties': {'summary':STR, 'decisions':{'type':'array','items':STR}, 'base_commit':STR, 'files':{'type':'array','maxItems':16,'items':{'type':'object','properties':{'path':STR,'start':{'type':'integer','minimum':1},'end':{'type':'integer','minimum':1},'note':STR,'sha256':STR},'required':['path'],'additionalProperties':False}}},'additionalProperties':False},
          'prepared_plan': {'type': 'object', 'properties': {'summary': STR, 'steps': {'type':'array','items':STR}, 'acceptance': {'type':'array','items':STR}, 'complexity': {'type':'string','enum':['small','standard','complex']}}, 'required':['summary','steps','acceptance','complexity'], 'additionalProperties':False}},
         ['project', 'objective', 'request_key']),
    tool('workflow_status', 'Read progress, current leader, model call budget and verification. No AI call.', {'workflow_id': STR, 'include_details':{'type':'boolean'}}, ['workflow_id']),
    tool('workflow_cancel', 'Cancel a workflow. Late old-leader results are ignored.', {'workflow_id': STR}, ['workflow_id']),
    tool('workflow_retry', 'Resume a blocked workflow after fixing the cause. Keeps existing quota cap unless extra_calls is explicitly granted.',
         {'workflow_id': STR, 'extra_calls': {'type': 'integer', 'minimum': 0, 'maximum': 20},
          'not_before': {'type': 'number', 'minimum': 0}, 'request_key': STR}, ['workflow_id']),
    tool('recover_context', 'Recover a registered project memory and unfinished workflows. Call before delegating again.', {'project': STR}, ['project']),
    tool('memory_note', 'Save a short project decision/checkpoint; do not store credentials.',
         {'project': STR, 'name': STR, 'content': STR}, ['project', 'name', 'content']),
]

TOOLS += [
    tool('list_agents', 'List installed/configured agents without model calls.', {}, []),
    tool('get_agent_status', 'Read one agent status; does not probe authentication or call a model.', {'agent': STR}, ['agent']),
    tool('get_agent_models', 'Read model policy and provider-reported model catalog; unknown remains unknown.', {'agent': STR}, ['agent']),
    tool('set_agent_enabled', 'Change enabled state only with operator-granted MCP configuration permission and no active workflow.',
         {'agent': STR, 'enabled': {'type': 'boolean'}, 'project': STR}, ['agent', 'enabled']),
    tool('set_agent_model', 'Change model policy only with operator-granted MCP configuration permission.',
         {'agent': STR, 'policy': {'type': 'string', 'enum': ['INHERIT', 'AUTO', 'MANUAL']},
          'model': STR, 'fallback': {'type': 'string', 'enum': ['INHERIT']}, 'project': STR}, ['agent', 'policy']),
    tool('initialize_project', 'Refresh context for an already registered approved project; cannot select arbitrary file paths.', {'project': STR}, ['project']),
    tool('get_project_context', 'Read versioned context and stale status for a registered project.', {'project': STR}, ['project']),
    tool('dispatch_task', 'Dispatch using the same durable workflow engine, enabled agents and request-key deduplication.',
         {'project': STR, 'objective': STR, 'request_key': STR,
          'max_calls': {'type': 'integer', 'minimum': 1, 'maximum': 50}}, ['project', 'objective', 'request_key']),
    tool('get_workflow_status', 'Read actual persisted workflow status.', {'workflow_id': STR}, ['workflow_id']),
    tool('get_workflow_events', 'Read actual persisted events without LLM polling.', {'workflow_id': STR}, ['workflow_id']),
    tool('cancel_workflow', 'Cancel via generation fencing; preserve code and checkpoints.', {'workflow_id': STR}, ['workflow_id']),
]


def serve(home, client='unknown'):
    """Serve local stdio JSON-RPC requests through the shared Hub without host-model calls."""
    hub = Hub(home)
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            if 'id' not in request:
                continue
            method = request.get('method')
            if method == 'initialize':
                requested = request.get('params', {}).get('protocolVersion', '2024-11-05')
                version = requested if requested in {'2024-11-05', '2025-03-26', '2025-06-18'} else '2024-11-05'
                result = {'protocolVersion': version, 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'agent-hub-private', 'version': '0.2.0'},
                          'instructions': 'For ordinary coding requests in a workspace initialized with ma init, use this Hub; '
                                          'the user does not need a special prompt prefix or a terminal ma run command. '
                                          'Call projects_list and match the exact current workspace Git root, then recover_context. '
                                          'Never guess a project or register an arbitrary path; ask if the workspace cannot be matched. '
                                          'Reuse an existing active workflow and prior context. Dispatch with workflow_start, a stable request_key '
                                          'and a prepared_plan/handoff when already available; do not implement a parallel workflow yourself. '
                                          'Do not change security flags or increase the call budget. '
                                          'The daemon handles retries and leader failover without model supervision. Do not repeatedly poll with AI; check status only when useful.'}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                from .config import load
                hub.config = load(hub.store.home)
                params = request.get('params', {})
                args = params.get('arguments', {})
                name = params.get('name')
                try:
                    aliases = {'dispatch_task': 'workflow_start', 'get_workflow_status': 'workflow_status',
                               'cancel_workflow': 'workflow_cancel'}
                    name = aliases.get(name, name)
                    if name == 'projects_list':
                        from .project_context import is_removed
                        value = [p for p in hub.store.all('SELECT id,name,path FROM projects') if not is_removed(hub.store.home, p['id'])]
                    elif name == 'workflow_start':
                        created = hub.start(**args)
                        hub.store.event(created['id'], 'client_dispatch', {'client': str(client)[:80]})
                        value = hub.brief(created['id'])
                    elif name == 'workflow_status':
                        details=args.pop('include_details',False)
                        value = hub.status(**args) if details else hub.brief(**args)
                    elif name == 'workflow_cancel':
                        value = hub.store.cancel(**args)
                    elif name == 'workflow_retry':
                        value = hub.retry(**args)
                    elif name == 'recover_context':
                        value = hub.recover(**args)
                    elif name == 'memory_note':
                        project = hub.store.project(args['project'])
                        hub.store.remember(project['id'], args['name'], args['content'])
                        value = {'saved': True}
                    elif name in {'list_agents', 'get_agent_status', 'get_agent_models'}:
                        from .registry import discover
                        rows = discover(hub.config, home=hub.store.home)
                        if name == 'list_agents':
                            value = rows
                        elif name == 'get_agent_models':
                            from .registry import model_info
                            value = model_info(hub.config, args['agent'], hub.store.home)
                        else:
                            value = next((r for r in rows if r['agent'] == args['agent']), None)
                            if value is None: raise ValueError('Unknown agent')
                    elif name in {'set_agent_enabled', 'set_agent_model'}:
                        if not hub.config.get('permissions', {}).get('mcp_config_write'):
                            raise ValueError('Operator must grant permission with ma config --allow-mcp-config true')
                        from .settings import update_provider
                        if name == 'set_agent_enabled':
                            changes = {'enabled': args['enabled']}
                        else:
                            changes = {'model_policy': args['policy'], 'model': args.get('model'), 'model_fallback': args.get('fallback')}
                            from .registry import model_info
                            changes['model_catalog'] = model_info(hub.config, args['agent'], hub.store.home)['catalog']
                        value = update_provider(hub, args['agent'], changes, args.get('project'))
                    elif name == 'initialize_project':
                        from .project_context import refresh
                        value = refresh(hub, hub.store.project(args['project']))
                    elif name == 'get_project_context':
                        from .project_context import get_context
                        value = get_context(hub, args['project'])
                    elif name == 'get_workflow_events':
                        hub.store.workflow(args['workflow_id'])
                        value = hub.store.all('SELECT kind,data,created FROM events WHERE workflow_id=? ORDER BY id DESC LIMIT 100', (args['workflow_id'],))
                    else:
                        raise ValueError('Unknown tool')
                    result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}]}
                except Exception as error:
                    result = {'isError': True, 'content': [{'type': 'text', 'text': str(error)}]}
            else:
                raise ValueError('Method not found')
            response = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
        except Exception as error:
            response = {'jsonrpc': '2.0', 'id': request.get('id') if isinstance(request, dict) else None,
                        'error': {'code': -32600, 'message': str(error)}}
        print(json.dumps(response, ensure_ascii=False), flush=True)
