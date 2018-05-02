import argparse
import json
import os
import sys

from .interview_kernel import Interview

from jupyter_client.kernelspec import KernelSpecManager
from IPython.utils.tempdir import TemporaryDirectory
import shutil
import errno
from pathlib import Path


kernel_json = {
    "argv": [
        sys.executable, "-m", "interview_kernel", "-f", "{connection_file}"],
    "display_name": "MoSIS",
    "language": "text",
    "name": "interview_kernel"
}


def install_my_kernel_spec(user=True, prefix=None):
    with TemporaryDirectory() as td:
        os.chmod(td, 0o755)  # Starts off as 700, not user readable
        with open(os.path.join(td, 'kernel.json'), 'w') as f:
            json.dump(kernel_json, f, sort_keys=True)
        try:
            interview = Interview(True)
            with open(os.path.join(td, 'kernel.js'), 'w') as f:
                # javascript code that sets an initial markdown cell in every new notebook
                js = """define(['base/js/namespace'], function(Jupyter)
                        {{
                            function onload()
                            {{
                                if (Jupyter.notebook.get_cells().length ===1)
                                {{
                                    Jupyter.notebook.insert_cell_above('markdown').set_text(`{}`);
                                    Jupyter.notebook.get_cell(0).render();
                                }}
                                console.log("interview kernel.js loaded")
                            }}
                            return {{
                                onload: onload
                            }};
                        }});""".format(interview.my_markdown_greeting.replace("`", "\\`"))

                f.write(js)
                # print(js)

        except Exception:
            print('could not copy kernel.js, will not see initial message in notebook')

        print("Installing Jupyter kernel spec")
        KernelSpecManager().install_kernel_spec(td, 'Interview', user=user, prefix=prefix)

        # copy exastencils directory to user's home
        src = Path(os.path.dirname(__file__)).joinpath("./exastencils")
        dest = Path.home().joinpath("./exastencils")
        try:
            shutil.copytree(src, dest)
        except OSError as e:
            # If the error was caused because the source wasn't a directory
            if e.errno == errno.ENOTDIR:
                shutil.copy(src, dest)
            else:
                print('Directory not copied. Error: %s' % e)


def _is_root():
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False  # assume not an admin on non-Unix platforms

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', action='store_true',
        help="Install to the per-user kernels registry. Default if not root.")
    ap.add_argument('--sys-prefix', action='store_true',
        help="Install to sys.prefix (e.g. a virtualenv or conda env)")
    ap.add_argument('--prefix',
        help="Install to the given prefix. "
             "Kernelspec will be installed in {PREFIX}/share/jupyter/kernels/")
    args = ap.parse_args(argv)

    if args.sys_prefix:
        args.prefix = sys.prefix
    if not args.prefix and not _is_root():
        args.user = True

    install_my_kernel_spec(user=args.user, prefix=args.prefix)

if __name__ == '__main__':
    main()
