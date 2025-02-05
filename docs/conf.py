# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
from pathlib import Path

import docutils.nodes
import sphinx.addnodes
from sphinx.application import Sphinx
from sphinx.builders import Builder
from sphinx.domains import Domain
from sphinx.environment import BuildEnvironment
from typing_extensions import override

# Allow autodoc to import modules
sys.path.insert(0, str(Path("..", "src").resolve()))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "oidc-provider-mock"
copyright = "© 2025- Thomas Scholtes"
author = "Thomas Scholtes"

github_url = f"https://github.com/geigerzaehler/{project}"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

default_role = "any"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "flask": ("https://flask.palletsprojects.com/en/stable/", None),
}

autodoc_typehints = "both"
autodoc_typehints_description_target = "documented"

myst_heading_anchors = 2

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output


templates_path = ["_templates"]
html_title = "OIDC Provider Mock"
html_theme = "shibuya"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {"github_url": f"https://github.com/geigerzaehler/{project}"}

github_ref = os.getenv("READTHEDOCS_GIT_IDENTIFIER", "main")
github_src_url = f"{github_url}/blob/{github_ref}"


class GithubSourceDomain(Domain):
    @override
    def resolve_any_xref(
        self,
        env: BuildEnvironment,
        fromdocname: str,
        builder: Builder,
        target: str,
        node: sphinx.addnodes.pending_xref,
        contnode: docutils.nodes.Element,
    ) -> list[tuple[str, docutils.nodes.Element]]:
        if not Path(__file__).parent.parent.joinpath(target).exists():
            return []

        reference = docutils.nodes.reference(
            refuri=f"{github_src_url}/{target}",
            internal=False,
        )
        reference.append(contnode)

        return [("github:link", reference)]


def setup(app: Sphinx):
    app.add_domain(GithubSourceDomain)
