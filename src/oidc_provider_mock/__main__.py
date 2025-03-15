import logging
import os
import sys
import time
import traceback
from datetime import timedelta

import click
import uvicorn

from . import app
from ._app import Config

_default_config = Config


@click.command(context_settings={"max_content_width": 100})
@click.option(
    "-p",
    "--port",
    help="Port to start server on",
    default=9400,
    show_default=True,
)
@click.option(
    "-r",
    "--require-registration",
    help="Require client to register before they can request authentication",
    show_default=True,
    flag_value=True,
    default=_default_config.require_client_registration,
    type=bool,
    is_flag=False,
)
@click.option(
    "-n",
    "--require-nonce",
    help="Require clients to include a nonce in the authorization request to prevent replay attacks",
    show_default=True,
    flag_value=True,
    default=_default_config.require_nonce,
    type=bool,
    is_flag=False,
)
@click.option(
    "-f",
    "--no-refresh-token",
    help="Do not issue an refresh token",
    show_default=True,
    flag_value=True,
    default=not _default_config.issue_refresh_token,
    type=bool,
    is_flag=False,
)
@click.option(
    "-e",
    "--token-max-age",
    help="Max age of access and ID tokens in seconds until they expire",
    default=_default_config.access_token_max_age.total_seconds(),
    type=int,
)
def run(
    port: int,
    *,
    require_registration: bool,
    require_nonce: bool,
    no_refresh_token: bool,
    token_max_age: int,
):
    """Start an OpenID Connect Provider for testing"""

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        Logfmter(
            color=not os.getenv("NO_COLOR")
            and (handler.stream.isatty() or bool(os.getenv("FORCE_COLOR")))
        )
    )
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    uvicorn.run(
        app(
            require_client_registration=require_registration,
            require_nonce=require_nonce,
            issue_refresh_token=not no_refresh_token,
            access_token_max_age=timedelta(seconds=token_max_age),
        ),
        interface="wsgi",
        port=port,
        log_config=None,
    )


_LOG_RECORD_ATTRIBUTES = (
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
)


_ANSI_RESET = "\033[0m"
_ANSI_BOLD = "\033[1m"
_ANSI_RED = "\033[31m"
_ANSI_YELLOW = "\033[33m"
_ANSI_BLUE = "\033[34m"
_ANSI_WHITE = "\033[37m"


class Logfmter(logging.Formatter):
    def __init__(self, color: bool):
        self._color = color

    def format(self, record: logging.LogRecord) -> str:
        out = ""

        log_time = time.localtime(record.created)
        out += f"{time.strftime('%H:%M:%S', log_time)}.{record.msecs:03.0f}"

        out += " "
        if self._color:
            if record.levelno >= logging.ERROR:
                out += _ANSI_RED
            elif record.levelno >= logging.WARNING:
                out += _ANSI_YELLOW
                level_name = "WARN"
            elif record.levelno >= logging.INFO:
                out += _ANSI_BLUE
            else:
                out += _ANSI_WHITE

        level_name = record.levelname
        if level_name == "WARNING":
            level_name = "WARN"
        out += f"{level_name:6s}"

        if self._color:
            out += _ANSI_RESET

        out += f" {record.name}"

        if isinstance(record.msg, dict):
            data: dict[str, object] = dict(record.msg)  # pyright: ignore
        else:
            data = {}

        data.update({
            key: value
            for key, value in record.__dict__.items()
            if key not in _LOG_RECORD_ATTRIBUTES
        })

        color_message = data.pop("color_message", None)
        unformatted_message = data.pop("_msg", None)
        if self._color and isinstance(color_message, str):
            if record.args:
                out += " " + color_message % record.args
            else:
                out += " " + color_message
        elif unformatted_message:
            out += " " + str(unformatted_message)
        else:
            out += " " + record.getMessage()

        for key, value in data.items():
            out += f" {self._format_key(key)}={self._format_value(value)}"

        if record.exc_info:
            formatted_exception = "\n".join(
                traceback.format_exception(record.exc_info[1])
            )

            out += f" {self._format_key('exc_info')}={self._format_value(formatted_exception)}"

        return out

    @classmethod
    def _format_value(cls, value: object) -> str:
        if value is None:
            return ""
        elif isinstance(value, bool):
            return "true" if value else "false"

        value = str(value)

        if '"' in value:
            value = value.replace('"', '\\"')

        if "\n" in value:
            value = value.replace("\n", "\\n")

        if " " in value or "=" in value:
            value = f'"{value}"'

        return value

    def _format_key(self, key: str) -> str:
        if self._color:
            return f"{_ANSI_BOLD}{key}{_ANSI_RESET}"
        else:
            return key


if __name__ == "__main__":
    run()
