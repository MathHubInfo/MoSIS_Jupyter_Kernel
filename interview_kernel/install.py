import argparse
import json
import os
import sys

from interview_kernel import Interview

from jupyter_client.kernelspec import KernelSpecManager
from IPython.utils.tempdir import TemporaryDirectory
from shutil import copyfile

kernel_json = Interview.kernel_json


def install_my_kernel_spec(user=True, prefix=None):
    with TemporaryDirectory() as td:
        os.chmod(td, 0o755) # Starts off as 700, not user readable
        with open(os.path.join(td, 'kernel.json'), 'w') as f:
            json.dump(kernel_json, f, sort_keys=True)
        # TODO: Copy any resources
        try:
            # copyfile('./kernel.js', os.path.join(td, 'kernel.js'))
            interview = Interview()
            with open(os.path.join(td, 'kernel.js'), 'w') as f:
                # javascript code that sets an initial markdown cell
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
                print(js)

        except Exception:
            print('could not copy kernel.js, will not see initial message in notebook')
            raise

        print("Installing Jupyter kernel spec")
        KernelSpecManager().install_kernel_spec(td, 'Interview', user=user, prefix=prefix)

def _is_root():
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False # assume not an admin on non-Unix platforms

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
