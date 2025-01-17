import re, os, sys

import idc
import ida_kernwin

PYTHON_DEFAULT_ENCODING = os.getenv("PYTHONIOENCODING", "utf-8")


class UnknowEncodingError(Exception):
    pass


class PythonFile(object):
    def __init__(self, path: str, cwd=None, argv=[], env={}, encoding=None):
        self.path = path
        self.cwd = cwd
        self.argv = [self.path]
        self.argv.extend(argv)
        self.env = env
        self.encoding = encoding

        if os.path.isabs(self.path):
            self.abspath = self.path
        else:
            self.abspath = os.path.join(self.cwd, self.path)

        self.globals = {"__name__": "__main__", "__file__": self.abspath}

        self.compile()

    def compile(self):
        if self.encoding is None:
            with open(self.abspath, "rb") as f:
                raw = f.read()

            try:
                code_text = raw.decode(PYTHON_DEFAULT_ENCODING)
                self.encoding = PYTHON_DEFAULT_ENCODING
            except UnicodeDecodeError:
                encoding_pat = re.compile(r"\s*#.*coding[:=]\s*([-\w.]+).*")
                for line in raw.decode(self.encoding, errors="replace").split("\n"):
                    match = encoding_pat.match(line)
                    if match:
                        self.encoding = match.group(1)
                        break

                if self.encoding is None:
                    raise UnknowEncodingError("unknow file encoding")
                code_text = raw.decode(self.encoding)
        else:
            with open(self.abspath, "r", encoding=self.encoding) as f:
                code_text = f.read()

        self.code = compile(code_text, self.abspath, "exec", optimize=0)

    def _before_exec(self):
        # patch
        self._orig_argv = sys.argv
        sys.argv = [self.path]
        self._orig_idc_argv = idc.ARGV
        idc.ARGV = self.argv
        self._orig_env = os.environ.copy()
        os.environ.update(self.env)
        self._orig_cwd = os.getcwd()
        os.chdir(self.cwd)
        self._orig_modules = sys.modules.copy()

        prapare_code = """
import debugpy
debugpy.debug_this_thread()
debugpy.wait_for_client()

import ida_kernwin
ida_kernwin.refresh_idaview_anyway()
        """
        prapare = compile(prapare_code, "", "exec")

        ida_kernwin.execute_sync(lambda: exec(prapare), ida_kernwin.MFF_WRITE)

    def exec(self):
        self._before_exec()
        ida_kernwin.execute_sync(
            lambda: exec(self.code, self.globals), ida_kernwin.MFF_WRITE
        )
        self._after_exec()

    def _after_exec(self):
        # restore
        sys.argv = self._orig_argv
        idc.ARGV = self._orig_idc_argv
        os.environ = self._orig_env
        os.chdir(self._orig_cwd)
        for k in list(sys.modules.keys()):
            if k not in self._orig_modules:
                # https://docs.python.org/3/reference/import.html#the-module-cache
                del sys.modules[k]


# https://docs.python.org/3.10/library/sys.html?highlight=sys%20path#sys.path
# > As initialized upon program startup, the first item of this list,
# > path[0], is the directory containing the script that was used to
# > invoke the Python interpreter.
# > If path[0] is the **empty string**, which directs Python to search modules 
# > in the current directory first.
if "" not in sys.path:
    sys.path.insert(0, "")
