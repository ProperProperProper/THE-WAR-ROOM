#!/usr/bin/env python3
"""MCP server for LLM routing, context management, and fine-tuning."""
import json
import sys
from pathlib import Path
import providers
from store import Store
from finetune_service import FineTuneService
from training_generator import generate_training_pairs, save_training_data

class MCPServer:
    def __init__(self, store_path):
        self.store = Store(store_path)
        self.finetune = FineTuneService(Path.home() / 'Documents')

    def handle_call(self, request):
        method = request.get('method')
        params = request.get('params', {})

        try:
            if method == 'query':
                return self.query(params['prompt'], params['workspace'], params.get('llm'), params.get('store_context', True))
            elif method == 'health':
                return self.health(params.get('llm'))
            elif method == 'context':
                return self.get_context(params['workspace'], params['llm'])
            elif method == 'clear_context':
                return self.clear_context(params['workspace'], params.get('llm'))
            elif method == 'compact':
                return self.compact(params['workspace'], params.get('llm'))
            elif method == 'finetune_validate':
                return self.finetune.validate_data(params['data_path'])
            elif method == 'finetune_omlx':
                return self.finetune.fine_tune_omlx(params['model'], params['data_path'],
                    params.get('epochs', 1), params.get('batch_size', 1))
            elif method == 'finetune_list':
                return self.finetune.list_adapters()
            elif method == 'finetune_remove':
                return self.finetune.remove_adapter(params['adapter_name'])
            elif method == 'generate_training_data':
                pairs = generate_training_pairs(params['folder_path'], max_files=params.get('max_files', 20))
                if isinstance(pairs, dict) and 'error' in pairs:
                    return pairs
                result = save_training_data(pairs)
                return result
            elif method == 'train_from_inbox':
                inbox_path = Path.home() / 'Downloads' / 'EthLadder-Training-Inbox'
                pairs = generate_training_pairs(str(inbox_path), max_files=100)
                if isinstance(pairs, dict) and 'error' in pairs:
                    return pairs
                if not pairs:
                    return {'error': 'No training data found in inbox'}
                data_result = save_training_data(pairs)
                if 'error' in data_result:
                    return data_result
                return self.finetune.fine_tune_omlx(
                    f"inbox-trained-{Path(data_result['path']).stem}",
                    data_result['path'],
                    params.get('epochs', 3),
                    params.get('batch_size', 1)
                )
            else:
                return {'error': f'Unknown method: {method}'}
        except Exception as e:
            return {'error': str(e)}

    def query(self, prompt, workspace, llm=None, store_context=True):
        """Query an LLM with optional context."""
        adapters = {'claude': providers.claude, 'codex': providers.codex, 'omlx': providers.omlx}

        if llm and llm not in adapters:
            return {'error': f'Unknown LLM: {llm}'}

        target_llms = [llm] if llm else list(adapters.keys())

        for name in target_llms:
            try:
                answer = adapters[name](prompt, workspace, self.store if store_context else None)
                return {'answer': answer, 'provider': name}
            except providers.ProviderError as e:
                if llm:  # If specific LLM requested, fail immediately
                    return {'error': str(e)}
                continue  # Try next provider

        return {'error': 'No provider available'}

    def health(self, llm=None):
        """Check provider health."""
        health_checks = {'claude': providers.claude_health, 'codex': providers.codex_health, 'omlx': providers.omlx_health}

        if llm:
            if llm not in health_checks:
                return {'error': f'Unknown LLM: {llm}'}
            return {llm: health_checks[llm]()}

        return {name: check() for name, check in health_checks.items()}

    def get_context(self, workspace, llm):
        """Retrieve saved context for an LLM."""
        return self.store.llm_context(workspace, llm)

    def clear_context(self, workspace, llm=None):
        """Clear context for an LLM or all LLMs in a workspace."""
        self.store.clear_llm_context(workspace, llm)
        return {'cleared': llm or 'all'}

    def compact(self, workspace, llm=None):
        """Compact context for an LLM or all LLMs in a workspace."""
        target_llms = [llm] if llm else ['claude', 'codex', 'omlx']
        for name in target_llms:
            ctx = self.store.llm_context(workspace, name)
            if ctx['messages']:
                ctx['messages'] = ctx['messages'][-5:]  # Keep only last 5 for compaction
                self.store.llm_context(workspace, name, ctx)
        return {'compacted': llm or 'all'}

def main():
    store_path = Path.home() / 'Documents' / '.war-room-state' / 'state.sqlite3'
    server = MCPServer(store_path)

    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = server.handle_call(request)
            print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            print(json.dumps({'error': 'Invalid JSON'}), flush=True)
        except Exception as e:
            print(json.dumps({'error': str(e)}), flush=True)

if __name__ == '__main__':
    main()
