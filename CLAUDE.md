# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tools

- `uv` for dependency and project management
- `ruff` for linting and formatting
- `pyright` for type checking

## Development Guidelines

- Always use type hints for function parameters and return values
- Never use `Any` type - prefer specific types or use union types when needed
- Use modern idiomatic Python code targeting Python 3.10+
- Follow existing code patterns and conventions in the codebase

## Architecture Overview

This is a mock OpenID Connect (OIDC) provider server for testing authentication flows. The architecture consists of:

### Core Components

- `_app.py`: Main Flask application factory and OAuth2/OIDC protocol implementation using Authlib
- `_server.py`: Threading utilities for running the server in background threads during tests
- `_storage.py`: In-memory storage models for clients, users, tokens, and authorization codes
- `_client.py`: Blueprint for OIDC client functionality and login flows
- `_client_lib.py`: OIDC client library for making requests to providers
- `__main__.py`: CLI interface using `click`

### Key Features

- **Dynamic client registration**: Clients can be registered at runtime or use "allow any" mode
- **User management**: Users can be added via HTTP API with custom claims
- **Token lifecycle**: Issues access tokens, ID tokens, and optionally refresh tokens
- **Authorization flows**: Supports authorization code flow with PKCE
- **Testing utilities**: Context managers for running server in tests

### Templates

HTML templates in `templates/` provide the authorization form UI:

- **`authorization_form.html`**: Main login/authorization form
- **`_base.html`**: Base template
- **`error.html`**: Error display
- **`index.html`**: Provider information page

### Protocol Implementation

- Uses **Authlib** for OAuth2/OIDC protocol compliance
- **Flask** for HTTP server and routing
- **Pydantic** for data validation
- **JOSE/JWT** for token signing and verification
- **RS256** algorithm for JWT signing

### Test Structure

- Tests use **pytest** with **Playwright** for browser automation
- **Flask-OIDC** integration examples in `examples/`
- **Typeguard** runtime type checking enabled in tests
- Coverage reporting configured for HTML and terminal output

### Configuration

- All configuration via `Config` dataclass in `_app.py`
- CLI options in `__main__.py` for common settings
- Environment-based configuration for colors and logging

