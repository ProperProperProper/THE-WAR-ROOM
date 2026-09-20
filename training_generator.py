#!/usr/bin/env python3
"""Generate training data by scanning code folders and extracting content."""
import json
import re
import sys
from pathlib import Path

def scan_folder(folder_path, max_files=40000, extensions=None):
    """Scan folder RECURSIVELY for code files from ALL subfolders."""
    if extensions is None:
        extensions = {'.py', '.js', '.ts', '.go', '.java', '.sol', '.md', '.txt', '.yml', '.yaml', '.json'}

    folder = Path(folder_path)
    if not folder.exists():
        return {'error': f'Folder not found: {folder_path}'}

    # Collect ALL files from all subfolders
    all_files = []
    for ext in extensions:
        all_files.extend(folder.rglob(f'*{ext}'))

    # Remove duplicates and sort
    all_files = sorted(set(all_files))

    # Skip certain paths
    skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build', '.egg-info', 'tests'}
    filtered_files = [f for f in all_files if not any(skip in f.parts for skip in skip_dirs)]

    file_data = []
    for file_path in filtered_files[:max_files]:
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            if len(content) < 200000 and len(content) > 30:  # Include more files
                file_data.append({
                    'path': str(file_path.relative_to(folder)),
                    'name': file_path.name,
                    'content': content[:4000]  # Larger chunks
                })
        except Exception:
            pass

    return file_data

def extract_training_pairs(file_info):
    """Extract training pairs from file content - ULTRA AGGRESSIVE."""
    content = file_info['content']
    pairs = []

    # 1. Extract function definitions with docstrings
    func_pattern = r'def\s+(\w+)\s*\([^)]*\):\s*"""([^"]*?)"""'
    for match in re.finditer(func_pattern, content, re.DOTALL):
        func_name, docstring = match.groups()
        if func_name and docstring and len(docstring) > 5:
            pairs.append({
                'instruction': f"What does {func_name}() do?",
                'output': f"{func_name}(): {docstring.strip()[:250]}"
            })

    # 2. Extract class definitions
    class_pattern = r'class\s+(\w+)[^:]*:\s*"""([^"]*?)"""'
    for match in re.finditer(class_pattern, content, re.DOTALL):
        class_name, docstring = match.groups()
        if class_name and docstring and len(docstring) > 5:
            pairs.append({
                'instruction': f"Explain the {class_name} class",
                'output': f"Class {class_name}: {docstring.strip()[:250]}"
            })

    # 3. Extract TODO, FIXME, NOTE comments
    todo_pattern = r'#\s*(TODO|FIXME|NOTE|BUG|HACK|WARNING):\s*(.{10,200})'
    for match in re.finditer(todo_pattern, content):
        label, comment = match.groups()
        pairs.append({
            'instruction': f"{label}: {comment.strip()[:80]}",
            'output': f"[{label}] {comment.strip()[:250]}"
        })

    # 4. Extract markdown headers
    if file_info['name'].endswith('.md'):
        md_pattern = r'#+\s+(.{5,100})\n+([^#]{20,400})'
        for match in re.finditer(md_pattern, content):
            header, desc = match.groups()
            if header and desc:
                pairs.append({
                    'instruction': header.strip(),
                    'output': desc.strip()[:300]
                })

    # 5. Extract code blocks
    code_pattern = r'```[\w]*\n(.{50,400}?)\n```'
    for match in re.finditer(code_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if len(code) > 30:
            pairs.append({
                'instruction': "Code example",
                'output': code[:350]
            })

    # 6. Extract config files
    if any(file_info['name'].endswith(ext) for ext in ['.yml', '.yaml', '.json', '.txt', '.cfg', '.conf']):
        if len(content) > 100:
            pairs.append({
                'instruction': f"Configuration: {file_info['name']}",
                'output': content[:400]
            })

    # 7. ULTRA: For ANY file, break into chunks and extract
    lines = content.split('\n')
    # Remove empty/comment-only lines
    clean_lines = [l for l in lines if l.strip() and not l.strip().startswith('#')]

    # Extract chunks of code
    for i in range(0, min(len(clean_lines), 50), 5):
        chunk = '\n'.join(clean_lines[i:i+8])
        if len(chunk) > 50 and len(chunk) < 500:
            pairs.append({
                'instruction': f"Code from {file_info['name']}",
                'output': chunk
            })

    # Extract ALL imports
    imports = [l for l in lines if l.strip().startswith(('import ', 'from '))if len(l) < 200]
    if imports:
        pairs.append({
            'instruction': f"Imports",
            'output': '\n'.join(imports[:10])
        })

    # Extract ALL constants/config
    for line in lines:
        if re.match(r'^[A-Z_][A-Z0-9_]*\s*=', line):
            pairs.append({
                'instruction': "Configuration/Constant",
                'output': line[:300]
            })

    return pairs[:20]  # Allow up to 20 pairs per file

def generate_training_pairs(folder_path, max_files=20):
    """Generate training pairs from code files in folder."""
    files = scan_folder(folder_path, max_files)
    if isinstance(files, dict) and 'error' in files:
        return files

    if not files:
        return {'error': 'No code files found in folder'}

    print(f"📁 Found {len(files)} code files")

    training_pairs = []
    for i, file_info in enumerate(files[:10], 1):
        print(f"  📄 {i}. {file_info['path']}", end='', flush=True)
        pairs = extract_training_pairs(file_info)
        if pairs:
            training_pairs.extend(pairs)
            print(f" → {len(pairs)} pairs")
        else:
            print(" (no content)")

    return training_pairs

def save_training_data(training_pairs, output_path=None):
    """Save training pairs as JSONL."""
    if isinstance(training_pairs, dict) and 'error' in training_pairs:
        return training_pairs

    if not output_path:
        output_path = Path.home() / 'Documents' / 'training_data.jsonl'
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        for pair in training_pairs:
            f.write(json.dumps(pair) + '\n')

    return {
        'success': True,
        'path': str(output_path),
        'examples': len(training_pairs)
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 training_generator.py <folder> [output.jsonl] [max_files]")
        sys.exit(1)

    folder = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else None
    max_files = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    print(f"🔍 Scanning {folder}...")
    pairs = generate_training_pairs(folder, max_files=max_files)

    if isinstance(pairs, dict) and 'error' in pairs:
        print(f"Error: {pairs['error']}")
        sys.exit(1)

    result = save_training_data(pairs, output)
    print(f"\n✅ Generated {result['examples']} training examples")
    print(f"   Saved to: {result['path']}")

if __name__ == '__main__':
    main()
