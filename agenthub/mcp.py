"""MCP stdio transport. stdout is reserved for JSON-RPC replies."""
import json
import sys
from .api import Hub


def tool(name, description, props, required):
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
         {'workflow_id': STR, 'extra_calls': {'type': 'integer', 'minimum': 0, 'maximum': 20}}, ['workflow_id']),
    tool('recover_context', 'Recover a registered project memory and unfinished workflows. Call before delegating again.', {'project': STR}, ['project']),
    tool('memory_note', 'Save a short project decision/checkpoint; do not store credentials.',
         {'project': STR, 'name': STR, 'content': STR}, ['project', 'name', 'content']),
]


def serve(home):
    hub = Hub(home)
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            if 'id' not in request:
                continue
            method = request.get('method')
            if method == 'initialize':
                result = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'agent-hub-private', 'version': '0.1.0'},
                          'instructions': 'Call projects_list then recover_context before creating work. Use stable request_key. '
                                          'The daemon handles retries and leader failover without model supervision. Do not repeatedly poll with AI; check status only when useful.'}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                params = request.get('params', {})
                args = params.get('arguments', {})
                name = params.get('name')
                try:
                    if name == 'projects_list':
                        value = hub.store.all('SELECT id,name,path FROM projects')
                    elif name == 'workflow_start':
                        created = hub.start(**args)
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
