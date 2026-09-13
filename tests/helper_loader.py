"""Import bin/omarchy-iptv (no .py suffix) as a module for unit tests."""
import importlib.machinery
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"


def load_helper():
    loader = importlib.machinery.SourceFileLoader("omarchy_iptv", str(HELPER))
    spec = importlib.util.spec_from_loader("omarchy_iptv", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
