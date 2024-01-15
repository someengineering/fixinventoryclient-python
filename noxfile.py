"""Nox sessions."""
import sys
from textwrap import dedent

import nox

try:
    from nox_poetry import Session
    from nox_poetry import session
except ImportError:
    message = f"""\
    Nox failed to import the 'nox-poetry' package.

    Please install it using the following command:

    {sys.executable} -m pip install nox-poetry"""
    raise SystemExit(dedent(message)) from None


package = "resotoclient"
python_version = "3.9"
nox.needs_version = ">= 2021.6.6"
nox.options.sessions = ("mypy", "pytest")


@session(python=python_version)
def mypy(session: Session) -> None:
    """Type-check using mypy."""
    args = session.posargs or ["resotoclient", "tests"]
    session.install(".[extras]")
    session.install("mypy", "pytest", "networkx")
    session.run("mypy", "--strict", "resotoclient", "tests")


@session(python=python_version)
def pytest(session: Session) -> None:
    """Test using pytest"""
    args = session.posargs or ["tests"]
    session.install(".")
    session.install("pytest", "networkx", "pytest-asyncio")
    session.run("pytest", *args)
