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
nox.options.sessions = ("safety", "pyright", "pytest")


@session(python=python_version)
def safety(session: Session) -> None:
    """Scan dependencies for insecure packages."""
    requirements = session.poetry.export_requirements()
    session.install("safety")
    session.run("safety", "check", "--full-report", f"--file={requirements}")


@session(python=python_version)
def pyright(session: Session) -> None:
    """Type-check using mypy."""
    args = session.posargs or ["resotoclient", "tests"]
    session.install(".[extras]")
    session.install("pyright", "pytest", "networkx")
    session.run("pyright", *args)


@session(python=python_version)
def pytest(session: Session) -> None:
    """Test using pytest"""
    args = session.posargs or ["tests"]
    session.install(".")
    session.install("pytest", "networkx")
    session.run("pytest", *args)
