#!/usr/bin/env -S uv run

import re
from collections.abc import Iterable
from pathlib import Path


def main():
    output_path = Path("README.md")
    template_path = Path("README.md.tpl")
    snippets = _extract_snippets((Path("examples/flask_oidc_example.py"),))

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return snippets.pop(name)

    template = template_path.read_text()

    with output_path.open("w") as output:
        output.write("<!-- THIS FILE HAS BEEN GENERATED FROM REAMDE.md.tpl -->\n")
        output.write(re.sub(r"SNIPPET (\S+)", replace, template))

    if snippets:
        raise RuntimeError(f"Unused snippets {','.join(snippets.keys())}")


def _extract_snippets(paths: Iterable[Path]):
    snippets = dict[str, str]()
    for path in paths:
        content = path.read_text()
        matches = re.findall(
            r"# SNIPPET (\S+)\n+(.*?)\n+# SNIPPET END", content, re.DOTALL
        )
        for name, code in matches:
            if name in snippets:
                raise ValueError(f"Duplicate snippet name {name}")
            snippets[name] = code

    return snippets


main()
