"""F-HARNESS-116 (2026-11-16): loading the helper writes no bytecode beside
the stub it loads.

tests/helper_loader.py loaded bin/omarchy-iptv with bytecode writing on, so
every suite run and every probe built on it wrote `bin/__pycache__/` into
the tree it loaded from, and `python3 -I` with PYTHONDONTWRITEBYTECODE=1
did not stop it (`-I` implies `-E`). The tree's folder is git-ignored; the
same load pointed at the live install is the write CLAUDE.md's never-touch
list records (2026-09-27). Asked of a copy of this tree's helper under a
scratch folder, with bytecode writing forced on first, so the answer does
not depend on how the suite was started.
"""
import pathlib
import shutil
import sys
import tempfile
import unittest

import helper_loader


class LoaderBytecodeTest(unittest.TestCase):
    def test_the_load_writes_no_pycache_beside_the_stub(self):
        folder = pathlib.Path(tempfile.mkdtemp(prefix="loader-bytecode-"))
        self.addCleanup(shutil.rmtree, str(folder), True)
        shutil.copytree(str(helper_loader.ROOT / "bin"), str(folder / "bin"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = False
        try:
            module = helper_loader.load_helper(stream_lookup=None, path=folder / "bin" / "omarchy-iptv")
            after = sys.dont_write_bytecode
        finally:
            sys.dont_write_bytecode = previous
        self.assertTrue(callable(module.main))
        self.assertFalse(after, "the loader did not put the previous setting back")
        self.assertEqual(sorted(p.name for p in (folder / "bin").iterdir()), ["helper", "omarchy-iptv"])
        self.assertEqual([p.name for p in (folder / "bin" / "helper").iterdir() if p.name == "__pycache__"], [])


if __name__ == "__main__":
    unittest.main()
