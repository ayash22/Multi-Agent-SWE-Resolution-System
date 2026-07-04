"""Unit tests for retrieval/ast_chunker.py -- verifies AST-aware chunking
produces correct, complete function/class/method boundaries, unlike naive
text chunking which would cut mid-function."""
from __future__ import annotations

import textwrap

from retrieval.ast_chunker import CodeChunk, _split_large_function, chunk_python_file

SAMPLE_SOURCE = textwrap.dedent('''\
    import os
    from collections import defaultdict

    class QueryParser:
        """Parses raw query strings into structured filters."""

        def parse(self, raw):
            """Splits raw into key:value filter pairs."""
            result = defaultdict(list)
            for token in raw.split():
                if ":" in token:
                    key, value = token.split(":", 1)
                    result[key].append(value)
            return dict(result)

        def reset(self):
            return {}

    def top_level_func(path):
        """Reads a file."""
        with open(path) as f:
            return f.read()
''')


def _write_sample(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text(SAMPLE_SOURCE)
    return str(p)


def test_chunks_class_and_methods_separately(tmp_path):
    path = _write_sample(tmp_path)
    chunks = chunk_python_file(path)
    names = [(c.chunk_type, c.qualified_name) for c in chunks]

    assert ("class", "QueryParser") in names
    assert ("method", "QueryParser.parse") in names
    assert ("method", "QueryParser.reset") in names
    assert ("function", "top_level_func") in names


def test_chunk_line_numbers_are_exact(tmp_path):
    path = _write_sample(tmp_path)
    chunks = chunk_python_file(path)
    parse_chunk = next(c for c in chunks if c.qualified_name == "QueryParser.parse")

    lines = SAMPLE_SOURCE.splitlines()
    # The chunk's recorded start/end lines should exactly bound the `def parse`
    # block in the original source (1-indexed).
    assert lines[parse_chunk.start_line - 1].strip().startswith("def parse")
    assert "return dict(result)" in lines[parse_chunk.end_line - 1]


def test_chunk_captures_full_function_no_truncation(tmp_path):
    """Regression test for the core claim of AST-aware chunking: a naive
    500-character text split would cut this function's for-loop in half.
    The AST chunk must contain the complete body including the return."""
    path = _write_sample(tmp_path)
    chunks = chunk_python_file(path)
    parse_chunk = next(c for c in chunks if c.qualified_name == "QueryParser.parse")

    assert "for token in raw.split():" in parse_chunk.code
    assert "return dict(result)" in parse_chunk.code
    assert parse_chunk.code.strip().startswith("def parse")


def test_imports_used_attribution(tmp_path):
    path = _write_sample(tmp_path)
    chunks = chunk_python_file(path)
    parse_chunk = next(c for c in chunks if c.qualified_name == "QueryParser.parse")
    reset_chunk = next(c for c in chunks if c.qualified_name == "QueryParser.reset")

    assert any("defaultdict" in imp for imp in parse_chunk.imports_used)
    # `reset` doesn't reference defaultdict, so it should not claim that import.
    assert not any("defaultdict" in imp for imp in reset_chunk.imports_used)


def test_docstrings_extracted(tmp_path):
    path = _write_sample(tmp_path)
    chunks = chunk_python_file(path)
    class_chunk = next(c for c in chunks if c.qualified_name == "QueryParser")
    assert class_chunk.docstring == "Parses raw query strings into structured filters."


def test_syntax_error_returns_empty_list(tmp_path):
    p = tmp_path / "broken.py"
    p.write_text("def broken(:\n    pass")
    assert chunk_python_file(str(p)) == []


def test_large_function_is_split_into_subchunks():
    body_lines = "\n".join(f"    x{i} = {i}" for i in range(300))
    source = f"def huge_function():\n{body_lines}\n    return x0\n"
    huge_chunk = CodeChunk(
        file_path="huge.py", chunk_type="function", name="huge_function",
        class_name=None, start_line=1, end_line=302, code=source,
    )
    sub_chunks = _split_large_function(huge_chunk)
    assert len(sub_chunks) > 1
    for sc in sub_chunks:
        assert sc.code.strip().startswith("def huge_function")
        assert len(sc.code.splitlines()) <= 200 + 5  # header overhead tolerance
