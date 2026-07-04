"""
AST-aware code chunking.

Naive text chunking (e.g. "split every 500 characters" or "split every N
lines") frequently cuts a function or class definition in half. That's
disastrous for a code-fix agent: it needs to see *whole* functions to reason
about a fix and needs correct line numbers to generate a patch that applies.

This module instead parses each file into an AST and emits one chunk per
top-level function or class definition (including nested methods as their
own chunks, with a pointer to their parent class), preserving:

  - decorators and docstring as part of the chunk
  - exact start_line / end_line (1-indexed, matching `git apply` line numbers)
  - the set of names imported at module level that the chunk actually
    references (imports_used) -- useful context for the coder agent so it
    doesn't invent imports that don't exist in the file.

For files >200 lines inside a single function (rare, but happens with large
generated code or deeply procedural functions), we further split at logical
block boundaries: top-level statements inside the function body (loops,
if/else blocks, try/except blocks), each becoming a sub-chunk that still
carries the full function signature + docstring as a header so it remains
self-contained for retrieval.

Python files use the stdlib `ast` module (exact, zero extra dependencies).
Non-Python files fall back to tree-sitter, which is language-agnostic, so the
same chunker works across JS/TS/Go/Java/etc. codebases that SWE-bench-like
tasks might touch in a broader deployment.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field


@dataclass
class CodeChunk:
    file_path: str
    chunk_type: str  # "function" | "method" | "class" | "block"
    name: str
    class_name: str | None
    start_line: int
    end_line: int
    code: str
    imports_used: list[str] = field(default_factory=list)
    docstring: str | None = None

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "chunk_type": self.chunk_type,
            "name": self.name,
            "class_name": self.class_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "code": self.code,
            "imports_used": self.imports_used,
            "docstring": self.docstring,
        }

    @property
    def qualified_name(self) -> str:
        if self.class_name:
            return f"{self.class_name}.{self.name}"
        return self.name


MAX_CHUNK_LINES = 200


def _get_module_imports(tree: ast.Module) -> dict[str, str]:
    """Maps a bound name -> the import statement's module/alias source, e.g.
    `from foo.bar import baz as qux` -> {"qux": "from foo.bar import baz as qux"}."""
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                imports[bound] = f"import {alias.name}" + (
                    f" as {alias.asname}" if alias.asname else ""
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                bound = alias.asname or alias.name
                src = f"from {'.' * node.level}{module} import {alias.name}"
                if alias.asname:
                    src += f" as {alias.asname}"
                imports[bound] = src
    return imports


def _used_names(node: ast.AST) -> set[str]:
    names = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            names.add(n.id)
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            names.add(n.value.id)
    return names


def _source_segment(lines: list[str], node: ast.AST) -> str:
    start = node.lineno - 1
    end = node.end_lineno
    # Include decorators, which ast.get_source_segment on the def node
    # itself would otherwise exclude.
    if hasattr(node, "decorator_list") and node.decorator_list:
        start = min(start, node.decorator_list[0].lineno - 1)
    return "\n".join(lines[start:end])


def _split_large_function(chunk: CodeChunk) -> list[CodeChunk]:
    """Splits a >200-line function chunk at top-level statement boundaries
    within its body, keeping the def signature + docstring as a shared
    header on every sub-chunk so each remains independently retrievable."""
    code_lines = chunk.code.splitlines()
    if len(code_lines) <= MAX_CHUNK_LINES:
        return [chunk]

    try:
        tree = ast.parse(chunk.code)
    except SyntaxError:
        return [chunk]

    func_node = next(
        (n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
        None,
    )
    if func_node is None or not func_node.body:
        return [chunk]

    header_end = func_node.body[0].lineno - 1
    header = "\n".join(code_lines[:header_end])

    sub_chunks = []
    block_start = header_end
    for i, stmt in enumerate(func_node.body):
        is_last = i == len(func_node.body) - 1
        next_start = func_node.body[i + 1].lineno - 1 if not is_last else len(code_lines)
        if (stmt.end_lineno - block_start) >= MAX_CHUNK_LINES // 4 or is_last:
            body_slice = "\n".join(code_lines[block_start:next_start])
            sub_code = header + "\n" + body_slice
            sub_chunks.append(CodeChunk(
                file_path=chunk.file_path,
                chunk_type="block",
                name=f"{chunk.name}[lines {block_start + chunk.start_line}-"
                     f"{next_start + chunk.start_line}]",
                class_name=chunk.class_name,
                start_line=block_start + chunk.start_line,
                end_line=min(next_start + chunk.start_line, chunk.end_line),
                code=sub_code,
                imports_used=chunk.imports_used,
                docstring=chunk.docstring,
            ))
            block_start = next_start

    return sub_chunks if sub_chunks else [chunk]


def chunk_python_file(file_path: str, source: str | None = None) -> list[CodeChunk]:
    """Parses one Python file into function/class-level chunks."""
    if source is None:
        with open(file_path, errors="ignore") as f:
            source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    module_imports = _get_module_imports(tree)
    chunks: list[CodeChunk] = []

    def imports_used_for(node: ast.AST) -> list[str]:
        used = _used_names(node)
        return sorted(module_imports[n] for n in used if n in module_imports)

    def docstring_for(node) -> str | None:
        return ast.get_docstring(node)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chunk = CodeChunk(
                file_path=file_path,
                chunk_type="function",
                name=node.name,
                class_name=None,
                start_line=node.lineno,
                end_line=node.end_lineno,
                code=_source_segment(lines, node),
                imports_used=imports_used_for(node),
                docstring=docstring_for(node),
            )
            chunks.extend(_split_large_function(chunk))

        elif isinstance(node, ast.ClassDef):
            class_chunk = CodeChunk(
                file_path=file_path,
                chunk_type="class",
                name=node.name,
                class_name=None,
                start_line=node.lineno,
                end_line=node.end_lineno,
                code=_source_segment(lines, node),
                imports_used=imports_used_for(node),
                docstring=docstring_for(node),
            )
            chunks.append(class_chunk)

            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_chunk = CodeChunk(
                        file_path=file_path,
                        chunk_type="method",
                        name=sub.name,
                        class_name=node.name,
                        start_line=sub.lineno,
                        end_line=sub.end_lineno,
                        code=_source_segment(lines, sub),
                        imports_used=imports_used_for(sub),
                        docstring=docstring_for(sub),
                    )
                    chunks.extend(_split_large_function(method_chunk))

    return chunks


def chunk_with_tree_sitter(file_path: str, language: str, source: str | None = None) -> list[CodeChunk]:
    """Language-agnostic fallback for non-Python files using tree-sitter.
    Chunks at function_definition / method_definition / class_definition
    node types, which are named consistently across tree-sitter grammars
    for JS/TS/Go/Java/Rust/etc.
    """
    try:
        import tree_sitter_languages
    except ImportError:
        raise RuntimeError(
            "tree-sitter support requires `pip install tree_sitter tree_sitter_languages`"
        )

    if source is None:
        with open(file_path, errors="ignore") as f:
            source = f.read()

    parser = tree_sitter_languages.get_parser(language)
    tree = parser.parse(bytes(source, "utf8"))
    lines = source.splitlines()

    target_types = {
        "function_definition", "function_declaration", "method_definition",
        "class_definition", "class_declaration",
    }
    chunks = []

    def walk(node, class_name=None):
        for child in node.children:
            if child.type in target_types:
                start_line = child.start_point[0] + 1
                end_line = child.end_point[0] + 1
                name_node = child.child_by_field_name("name")
                name = source[name_node.start_byte:name_node.end_byte] if name_node else "<anon>"
                is_class = "class" in child.type
                chunks.append(CodeChunk(
                    file_path=file_path,
                    chunk_type="class" if is_class else ("method" if class_name else "function"),
                    name=name,
                    class_name=class_name,
                    start_line=start_line,
                    end_line=end_line,
                    code="\n".join(lines[start_line - 1:end_line]),
                    imports_used=[],
                    docstring=None,
                ))
                walk(child, class_name=name if is_class else class_name)
            else:
                walk(child, class_name=class_name)

    walk(tree.root_node)
    return chunks


LANGUAGE_BY_EXT = {
    ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
    ".tsx": "tsx", ".go": "go", ".java": "java", ".rb": "ruby",
    ".rs": "rust", ".c": "c", ".cpp": "cpp", ".h": "c",
}


def chunk_file(file_path: str) -> list[CodeChunk]:
    ext = os.path.splitext(file_path)[1]
    if ext == ".py":
        return chunk_python_file(file_path)
    if ext in LANGUAGE_BY_EXT:
        try:
            return chunk_with_tree_sitter(file_path, LANGUAGE_BY_EXT[ext])
        except RuntimeError:
            return []
    return []


def chunk_repo(repo_root: str, extensions: tuple[str, ...] = (".py",)) -> list[CodeChunk]:
    """Walks a repo and chunks every matching source file, skipping common
    non-source directories."""
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    all_chunks: list[CodeChunk] = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if fname.endswith(extensions):
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, repo_root)
                chunks = chunk_file(fpath)
                for c in chunks:
                    c.file_path = rel
                all_chunks.extend(chunks)
    return all_chunks


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="AST-aware code chunker")
    parser.add_argument("repo_root")
    parser.add_argument("--out", default="chunks.jsonl")
    args = parser.parse_args()

    chunks = chunk_repo(args.repo_root)
    with open(args.out, "w") as f:
        for c in chunks:
            f.write(json.dumps(c.to_dict()) + "\n")
    print(f"Wrote {len(chunks)} chunks from {args.repo_root} to {args.out}")
