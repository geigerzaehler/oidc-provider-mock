import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import timedelta
from typing import TYPE_CHECKING

import werkzeug.serving

if TYPE_CHECKING:
    from _typeshed.wsgi import WSGIApplication

from ._app import app

assert __package__


def run_server_in_thread(
    port: int = 0,
    *,
    require_client_registration: bool = False,
    require_nonce: bool = False,
    issue_refresh_token: bool = True,
    access_token_max_age: timedelta = timedelta(hours=1),
) -> AbstractContextManager[werkzeug.serving.BaseWSGIServer]:
    """Run a OIDC provider server on a background thread.

    The server is stopped when the context ends.

    See `app <oidc_provider_mock.app>` for documentation of parameters.

    >>> with run_server_in_thread(port=25432) as server:
    ...     print(f"Server listening at http://localhost:{server.server_port}")
    Server listening at http://localhost:25432

    """
    return _threaded_server(
        port=port,
        app=app(
            require_client_registration=require_client_registration,
            require_nonce=require_nonce,
            issue_refresh_token=issue_refresh_token,
            access_token_max_age=access_token_max_age,
        ),
    )


@contextmanager
def _threaded_server(
    app: "WSGIApplication",
    *,
    host: str = "localhost",
    port: int = 0,
    poll_interval: float = 0.1,
) -> Iterator[werkzeug.serving.ThreadedWSGIServer]:
    server = werkzeug.serving.make_server(
        host,
        port,
        app,
        threaded=True,
    )

    assert isinstance(server, werkzeug.serving.ThreadedWSGIServer)

    def run():
        try:
            server.serve_forever(poll_interval)
        finally:
            server.server_close()

    server_thread = threading.Thread(target=run)
    server_thread.start()

    try:
        yield server

    finally:
        shutdown_thread = threading.Thread(target=server.shutdown)
        shutdown_thread.start()
        shutdown_thread.join(1)
        if shutdown_thread.is_alive():
            raise TimeoutError("Server failed to shut down in time")

        server_thread.join(0.5)
        if server_thread.is_alive():
            raise TimeoutError("Server thread timed out")
