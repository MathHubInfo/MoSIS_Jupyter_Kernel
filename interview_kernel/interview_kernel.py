from os.path import join
#from pathlib import Path

from metakernel import MetaKernel
from IPython.display import HTML, Javascript
from metakernel import IPythonKernel
import ipywidgets as widgets

# http://mattoc.com/python-yes-no-prompt-cli.html
# https://github.com/phfaist/pylatexenc for directly converting Latex commands to unicode
from pylatexenc.latex2text import LatexNodes2Text
import getpass
from bokeh.io import output_notebook

from . import pde_state_machine
#import pde_state_machine
from . import string_handling
#import string_handling
from distutils.util import strtobool


"""This is a Jupyter kernel derived from MetaKernel. To use it, install it with the install.py script and run 
"jupyter notebook --debug --NotebookApp.token='' " from terminal. """


class Interview(MetaKernel):

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

        self.update_prompt()
        # bokeh notebook setup
        output_notebook()

    def set_initial_message(self, install_run=False):
        # set it up -- without server communication capabilities if we are just installing
        self.state_machine = pde_state_machine.PDE_States(self.poutput, self.update_prompt, self.please_prompt,
                                                     self.display_html, install_run)
        # already send some input to state machine, to capture initial output and have it displayed via kernel.js
        # /  not displayed in the real thing
        self.state_machine.handle_state_dependent_input("anything")   # TODO compatibility with not-notebook?
        my_markdown_greeting = Interview.banner + self.poutstring
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

        arg = string_handling.replace_times_to_cdot(LatexNodes2Text().latex_to_text(code))

        if not self.keyword_handling(arg):
            if not self.prompt_input_handling(arg):
                self.state_machine.handle_state_dependent_input(arg)

        if not silent:
            if self.outstream_name == "stderr": #TODO make errors markdown but red
                # string output
                stream_content = {'name': self.outstream_name, 'text': self.poutstring}
                self.send_response(self.iopub_socket, 'stream', stream_content)
            #    data_content = {
            #                        "ename": "InterviewError",
            #                        "evalue": self.poutstring,
            #                        "traceback": [self.poutstring],
            #                    }
            #    self.send_response(self.iopub_socket, 'error', data_content)
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

    def please_prompt(self, query, if_yes, if_no=None, pass_other=False):
        self.poutput(str(query)) # + " [y/n]? ")
        self.state_machine.prompted = True
        self.state_machine.if_yes = if_yes
        self.state_machine.if_no = if_no
        self.state_machine.pass_other = pass_other
        self.display_widget()

    def prompt_input_handling(self, arg):  # TODO make this widget-ed
        """ If we asked for a yes-no answer, execute what was specified in please_prompt.
        return true if the input was handled here, and false if not."""
        if self.state_machine.prompted:
            if arg == "":
                ret = True
            else:
                try:
                    ret = strtobool(str(arg).strip().lower())
                except ValueError:
                    if self.state_machine.pass_other:
                        return False
                    # or use as input to callback an input processing fcn..?
                    self.poutput("Please answer with y/n")
                    return True
            self.state_machine.prompted = False
            if ret:
                if self.state_machine.if_yes is not None:
                    self.state_machine.if_yes()
            elif self.state_machine.if_no is not None:
                self.state_machine.if_no()
            return True
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
        print(tgview_url)

    def display_widget(self):
        # needs jupyter nbextension enable --py widgetsnbextension
        from IPython.display import display
        from IPython.core.formatters import IPythonDisplayFormatter
        w = widgets.ToggleButton(
            value=False,
            description='Click me',
            disabled=False,
            button_style='', # 'success', 'info', 'warning', 'danger' or ''
            tooltip='Description',
            icon='check'
        )
        f = IPythonDisplayFormatter()
        # these should all do it, but all return the same string
        #f(w) # = "ToggleButton(value=False, description='Click me', icon='check', tooltip='Description')"
        #self._ipy_formatter(w)  # = "
        #display(w) # = "
        # self.Display(w)  # = "
        widgets.ToggleButton(
            value=False,
            description='Click me',
            disabled=False,
            button_style='',  # 'success', 'info', 'warning', 'danger' or ''
            tooltip='Description',
            icon='check'
        )


if __name__ == '__main__':
    # from ipykernel.kernelapp import IPKernelApp
    # IPKernelApp.launch_instance(kernel_class=Interview)
    Interview.run_as_main()
