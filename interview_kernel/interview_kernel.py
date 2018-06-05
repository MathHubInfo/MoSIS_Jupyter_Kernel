from os.path import join
#from pathlib import Path

from metakernel import MetaKernel
from IPython.display import HTML, Javascript, display
from metakernel import IPythonKernel
import ipywidgets as widgets

# http://mattoc.com/python-yes-no-prompt-cli.html
# https://github.com/phfaist/pylatexenc for directly converting Latex commands to unicode
from pylatexenc.latex2text import LatexNodes2Text
import getpass
from bokeh.io import output_notebook

from .widget_factory import WidgetFactory
from . import pde_state_machine
#import pde_state_machine
from . import string_handling
#import string_handling
from distutils.util import strtobool

from IPython.core import release
from ipython_genutils.py3compat import builtin_mod, PY3, unicode_type, safe_unicode
from IPython.utils.tokenutil import token_at_cursor, line_at_cursor
from traitlets import Instance, Type, Any, List, Bool
from ipykernel.kernelbase import Kernel
from ipykernel.comm import CommManager
import ipywidgets as widgets
from ipykernel.zmqshell import ZMQInteractiveShell


"""This is a Jupyter kernel derived from MetaKernel. To use it, install it with the install.py script and run 
"jupyter notebook --debug --NotebookApp.token='' " from terminal. """


class Interview(MetaKernel):
    shell = Instance('IPython.core.interactiveshell.InteractiveShellABC',
                     allow_none=True)
    shell_class = Type(ZMQInteractiveShell)

    use_experimental_completions = Bool(True,
                                        help="Set this flag to False to deactivate the use of experimental IPython completion APIs.",
                                        ).tag(config=True)

    user_module = Any()

    def _user_module_changed(self, name, old, new):
        if self.shell is not None:
            self.shell.user_module = new

    user_ns = Instance(dict, args=None, allow_none=True)

    def _user_ns_changed(self, name, old, new):
        if self.shell is not None:
            self.shell.user_ns = new
            self.shell.init_user_ns()


    implementation = 'Interview'
    implementation_version = '1.0'
    language = 'text'
    language_version = '1.0'
    language_info = {
        'name': 'text',
        'mimetype': 'text/plain',
        'file_extension': '.txt',
        'help_links': MetaKernel.help_links,
    }

    banner = \
"""**Hello, """ + getpass.getuser() + """! I am MoSIS 1.0, your partial differential equations and simulations tool.**
Let's set up a model and simulation.

To see a recap of what we know so far, enter `recap <optional keyword>`. 
To interactively visualize the current theory graph, enter `tgwiev` or `tgview mpd`. 
Otherwise, you can always answer with \LaTeX-type input.
"""
    #To get explanations, enter `explain <optional keyword>`.
    #You can inspect the currently loaded MMT theories under http://localhost:43397  #TODO

    def __init__(self, install_run=False, **kwargs):

        # call superclass constructor
        super(Interview, self).__init__(**kwargs)

        # To make custom magics happen, cf. https://github.com/Calysto/metakernel
        # from IPython import get_ipython
        # from metakernel import register_ipython_magics
        # register_ipython_magics()

        self.poutstring = ""# to collect string output to send
        self.outstream_name = 'stdout'

        self.state_machine, self.my_markdown_greeting = self.set_initial_message(install_run)
        self.toggle_button_counter = 0

        # Initialize the InteractiveShell subclass
        self.shell = self.shell_class.instance(parent=self,
                                               profile_dir=self.profile_dir,
                                               user_module=self.user_module,
                                               user_ns=self.user_ns,
                                               kernel=self,
                                               )
        self.shell.displayhook.session = self.session
        self.shell.displayhook.pub_socket = self.iopub_socket
        self.shell.displayhook.topic = self._topic('execute_result')
        self.shell.display_pub.session = self.session
        self.shell.display_pub.pub_socket = self.iopub_socket

        self.comm_manager = CommManager(parent=self, kernel=self)

        self.shell.configurables.append(self.comm_manager)
        comm_msg_types = ['comm_open', 'comm_msg', 'comm_close']
        for msg_type in comm_msg_types:
            self.shell_handlers[msg_type] = getattr(
                self.comm_manager, msg_type)

        self.widget_factory = WidgetFactory()

        self.update_prompt()
        # bokeh notebook setup
        # output_notebook()

    def set_initial_message(self, install_run=False):
        # set it up -- without server communication capabilities if we are just installing
        self.state_machine = pde_state_machine.PDE_States(self.poutput, self.update_prompt,
                                                     self.display_html, install_run, self.toggle_show_button)
        # already send some input to state machine, to capture initial output and have it displayed via kernel.js
        # /  not displayed in the real thing
        self.state_machine.handle_state_dependent_input("anything")   # TODO compatibility with not-notebook?
        # my_markdown_greeting = Interview.banner + self.poutstring
        my_markdown_greeting = str(Interview.banner) + self.poutstring
        self.poutstring = ""
        return self.state_machine, my_markdown_greeting

    def poutput(self, text, outstream_name='stdout'):
        """Accumulate the output here"""
        self.poutstring += str(text) + "\n"
        self.outstream_name = outstream_name

    ############# input processing if not explain or undo
    # def do_execute(self, code, silent=False, store_history=True, user_expressions=None,
    #                allow_stdin=False):
    def do_execute_direct(self, code, silent=False, allow_stdin=True):
        """This is where the user input enters our code"""

        arg = string_handling.replace_times_to_cdot(LatexNodes2Text().latex_to_text(code)).strip()

        if not self.keyword_handling(arg):
            if not self.prompt_input_handling(arg):
                self.state_machine.handle_state_dependent_input(arg)

        if not silent:
            if self.outstream_name == "stderr": #TODO make errors markdown but red
                # string output
                stream_content = {'name': self.outstream_name, 'text': self.poutstring}
                self.send_response(self.iopub_socket, 'stream', stream_content)
            else:
                # for other mime types, cf. http://ipython.org/ipython-doc/stable/notebook/nbformat.html
                data_content = {"data": {
                                            "text/markdown": self.poutstring,
                                        },
                                "metadata": {}
                                }
                self.send_response(self.iopub_socket, 'display_data', data_content)

        self.poutstring = ""
        self.outstream_name = 'stdout'

        return  # stream_content['text']


    def prompt_input_handling(self, arg):  # TODO make this widget-ed
        return False

    def keyword_handling(self, arg):
        """ If keywords for special meta-functions are given,
        executes the corresponding functions and returns true if it did."""
        if arg.startswith("explain"):
            self.state_machine.explain(arg)
            return True
        if arg.startswith("recap"):
            self.state_machine.recap(arg)
            return True
        if arg.startswith("tgview"):
            self.display_tgview(arg)
            return True
        if arg.startswith("undo"):
            self.do_undo(arg)
            return True
        if arg.startswith("widget"):
            self.display_widget()
            return True
        if arg.startswith("omdoc"):
            self.poutput(self.state_machine.mmtinterface.get_omdoc_theories())
            return True
        return False

    # called when user types 'explain [expression]'
    def do_explain(self, expression):
        "Explain an expression or the theoretical background to what we are currently looking for"
        if expression:
            explanation = "hello, " + expression  # TODO query flexiformal content through mmt
        else:
            explanation = 'hello'
        self.poutput(explanation)

    def help_explain(self):
        self.poutput('\n'.join(['explain [expression]',
                                'explain the expression given or the theory currently used',
                                ]))

    # called when user types 'undo'
    def do_undo(self, expression):
        "Go back to the last question"
        self.state_machine.trigger('last_state')

    def help_undo(self):
        self.poutput('\n'.join(['undo',
                                'Go back to the last question',
                                ]))

    def update_prompt(self):
        self.prompt = "(" + self.state_machine.state + ")" #TODO

    def toggle_show_button(self, button_text, hidden_text):
        # have a running id to uniquely identify the texts and buttons
        self.toggle_button_counter += 1
        counter_str = str(self.toggle_button_counter)
        # use html line breaks and have html display verbatim
        hidden_text = hidden_text.replace("\n", "<br>")

        self.Display(HTML('''
                    <div id="stacktrace''' + counter_str + '''"  style="display:none;"> ''' + hidden_text + '''</div>
                    <input id="button''' + counter_str + '''" type="button" name="button''' + counter_str + '''" value="''' + button_text + '''" onclick="toggle()" />
                    <script>
                        function toggle() {
                            var elem = document.getElementById("button''' + counter_str + '''")
                            if(elem.value == "''' + button_text + '''"){
                                elem.value = "Hide";
                                document.getElementById("stacktrace''' + counter_str + '''").style.display = "block";
                            }
                            else {
                                elem.value = "''' + button_text + '''";
                                document.getElementById("stacktrace''' + counter_str + '''").style.display = "none";
                            }
                        }
                    </script>
            '''))

    # tab completion for empty lines
    def do_complete(self, code, cursor_pos):
        """Override of cmd2 method which completes command names both for command completion and help."""
        # define the "default" input for the different states we can be in
        state_dependent_default_input = {
            'greeting': 'hi',
            'dimensions': '1',
            'domain': ['Ω = [ 0 ; 1 ]'],
            'unknowns': ['u : Ω → ℝ'],
            'parameters': ['f :  ℝ → ℝ = [x: ℝ] x '],  # ['f : Ω → ℝ = [x:Ω] x ⋅ x'],
            'pdes': ['∆u = f(x)'],
            'bcs': ['u = 0'],  # ,'u (1) = x_1**2'],
            'sim': ['FD'],
        }
        if not code or state_dependent_default_input[self.state_machine.state].startswith(code):
            return state_dependent_default_input[self.state_machine.state]
        else:
            # Call super class method.
            super(Interview, self).do_complete(code, cursor_pos)
            return

    def display_html(self, code=None):

        # highlight some of the code entered and show line numbers (just to play around)
        #self.Display(HTML("""
        #<style type="text/css">
        #      .styled-background { background-color: #ff7; }
        #</style>
        #<script>
        #if (typeof markedText !== 'undefined') {
        #        markedText.clear();
        #}
        #IPython.notebook.select_prev()
        #var cell = IPython.notebook.get_selected_cell();
        #markedText = cell.code_mirror.markText({line: %s, col: %s},
        #                                       {line: %s, col: %s},
        #                                       {className: "styled-background"});
        #cell.show_line_numbers(1)
        #IPython.notebook.select_next()
        #</script>
        #                    """ % (1, 0, 3, 0)))

        output_notebook()
        if code:
            self.Display(HTML(code))

    def display_tgview(self, args=''):
        """displays the theory graph viewer as html, cf. https://github.com/UniFormal/TGView/wiki/"""

        args = args.replace("tgview", '', 1).strip()

        server_url = str(self.state_machine.mmtinterface.mmt_frontend_base_url)

        if args == '':
            url_args_dict = dict(type="pgraph",
                                 graphdata=self.state_machine.mmtinterface.namespace)
            # if applicable, highlight the ephemeral parts https://github.com/UniFormal/TGView/issues/25
            thynames = string_handling.get_recursively(self.state_machine.simdata, "theoryname")
            # if thynames:
            #    url_args_dict["highlight"] = ",".join(thynames)
            # for now, highlight the "persistent ephemeral" theories, cf https://github.com/UniFormal/MMT/issues/326
            url_args_dict["highlight"] = "actual*,ephemeral*,u,q,α,SHE"
        else:
            model_name = self.state_machine.generate_mpd_theories()
            if model_name is None:
                model_name = "Model"
            url_args_dict = dict(type="mpd",
                                 graphdata=self.state_machine.mmtinterface.namespace + "?" + model_name,
                                 highlight="MPD_pde*")

        # have the side bars go away
        url_args_dict["viewOnlyMode"] = "true"

        tgview_url = string_handling.build_url(server_url, "graphs/tgview.html", args_dict=url_args_dict)

        code = """
            <iframe 
                src="{}" 
                style="width: 100%; height: 510px; border: none"
            >
            </iframe>
        """.format(tgview_url)

        self.display_html(code)
        # print(tgview_url)

    def start(self):
        self.shell.exit_now = False
        super(Interview, self).start()

    def set_parent(self, ident, parent):
        """Overridden from parent to tell the display hook and output streams
        about the parent message.
        """
        super(Interview, self).set_parent(ident, parent)
        self.shell.set_parent(parent)

    def init_metadata(self, parent):
        """Initialize metadata.
        Run at the beginning of each execution request.
        """
        md = super(Interview, self).init_metadata(parent)
        # FIXME: remove deprecated ipyparallel-specific code
        # This is required for ipyparallel < 5.0
        md.update({
            'dependencies_met': True,
            'engine': self.ident,
        })
        return md


if __name__ == '__main__':
    # from ipykernel.kernelapp import IPKernelApp
    # IPKernelApp.launch_instance(kernel_class=Interview)
    Interview.run_as_main()
