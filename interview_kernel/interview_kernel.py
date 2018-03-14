from sys import executable
from os.path import join
#from pathlib import Path
from metakernel import MetaKernel
from IPython.display import HTML, Javascript
from metakernel import IPythonKernel

# http://mattoc.com/python-yes-no-prompt-cli.html
# https://github.com/phfaist/pylatexenc for directly converting Latex commands to unicode
from pylatexenc.latex2text import LatexNodes2Text
import getpass
import matplotlib
matplotlib.use('nbagg')
import matplotlib.pyplot as plt
from bokeh.io import output_notebook, show, export_svgs
from bokeh.plotting import figure
from bokeh.resources import CDN
from bokeh.embed import file_html, components#, notebook_div
from bokeh.models import ColumnDataSource
#from tempfile import NamedTemporaryFile

from pde_state_machine import *

# This "main class" is two things: a REPL loop, by subclassing the cmd2 Cmd class
# and a state machine as given by the pytransitions package
class Interview(MetaKernel):
    implementation = 'Interview'
    implementation_version = '1.0'
    language = 'text'
    language_version = '0.1'
    language_info = {
        'name': 'text',
        'mimetype': 'text/plain',
        'file_extension': '.txt',
        'help_links': MetaKernel.help_links,
    }
    banner = "Interview kernel\n\n" \
             "Hello, " + getpass.getuser() + "! I am " + "TheInterview" + \
             ", your partial differential equations and simulations expert. " \
             "Let's set up a simulation together.\n" \
             "Please enter anything to start the interview."

    kernel_json = {
        "argv": [
            executable, "-m", "interview_kernel", "-f", "{connection_file}"],
        "display_name": "TheInterview",
        "language": "text",
        "name": "interview_kernel"
    }

    def __init__(self, **kwargs):

        self.state_machine = PDE_States(self.poutput, self.update_prompt, self.please_prompt)

        # call superclass constructor
        super(Interview, self).__init__(**kwargs)

        self.do_execute("%matplotlib nbagg")
        #plt.ion()

        # To make custom magics happen, cf. https://github.com/Calysto/metakernel
        # from IPython import get_ipython
        # from metakernel import register_ipython_magics
        # register_ipython_magics()

        self.update_prompt()
        self.poutstring = ""# to collect string output to send
        self.outstream_name = 'stdout'
        self.richcontent = None  # to collect rich contents (images etc)

        # bokeh notebook setup
        output_notebook()

    def poutput(self, text, outstream_name='stdout'):
        """Accumulate the output here"""
        self.poutstring += str(text) + "\n"
        self.outstream_name = outstream_name

    ############# input processing if not explain or undo
    # def do_execute(self, code, silent=False, store_history=True, user_expressions=None,
    #                allow_stdin=False):
    def do_execute_direct(self, code, silent=False):
        """This is where the user input enters our code"""

        arg = LatexNodes2Text().latex_to_text(code)

        if not self.keyword_handling(arg):
            if not self.prompt_input_handling(arg):
                self.state_machine.handle_state_dependent_input(arg)

        if not silent:
            stream_content = {'name': self.outstream_name, 'text': self.poutstring}
            self.send_response(self.iopub_socket, 'stream', stream_content)

        if self.richcontent is not None:
            # We send the display_data message with the contents.
            self.send_response(self.iopub_socket, 'display_data', self.richcontent)

            self.richcontent = None

        self.poutstring = ""
        self.outstream_name = 'stdout'

        return  # stream_content['text']

    def please_prompt(self, query, if_yes, if_no=None, pass_other=False):
        self.poutput(str(query) + " [y/n]? ")
        self.state_machine.prompted = True
        self.state_machine.if_yes = if_yes
        self.state_machine.if_no = if_no
        self.state_machine.pass_other = pass_other

    def prompt_input_handling(self, arg):
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
        if arg.startswith("html"):
            self.display_html()
            return True
        if arg.startswith("plt"):
            self.display_plt()
            return True
        if arg.startswith("bokeh"):
            self.display_bokeh()
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

    def do_shutdown(self, restart):
        self.state_machine.mmtinterface.exit_mmt()

        return super(Interview, self).do_shutdown(restart)

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

    def display_html(self):
        self.Display(HTML("""
        <style type="text/css">
              .styled-background { background-color: #ff7; }
        </style>
        <script>
        if (typeof markedText !== 'undefined') {
                markedText.clear();
        }
        IPython.notebook.select_prev()
        var cell = IPython.notebook.get_selected_cell();
        markedText = cell.code_mirror.markText({line: %s, col: %s},
                                               {line: %s, col: %s},
                                               {className: "styled-background"});
        cell.show_line_numbers(1)
        IPython.notebook.select_next()
        </script>
                            """ % (1, 0, 3, 0)))

        tgview_url = join(self.state_machine.mmtinterface.serverInstance, "graphs/tgview.html?type=thgraph&graphdata=", self.state_machine.mmtinterface.URIprefix, self.state_machine.mmtinterface.namespace + "?u")

        othercode = """
            <iframe 
                src="https://mmt.mathhub.info/graphs/tgview.html" 
                style="width: 100%; height: 510px; border: none"
            >
            </iframe>
        """
        # a futile attempt to set the size
        metadata = {
                        #'text/html': {
                            'width': 1600,
                            'height': 1400
                        #}
                    }
        self.Display(HTML(othercode, metadata=metadata))

    # cf. nbviewer.jupyter.org/github/bokeh/bokeh-notebooks/blob/master/tutorial/01 - Basic Plotting.ipynb
    def display_bokeh(self):
        from exaoutput import ExaOutput, ExaRunner

        # create a new plot with default tools, using figure
        p = figure(plot_width=1000, plot_height=400)

        runner = ExaRunner(ExaOutput())
        data = runner.load_data("u")
        #source = ColumnDataSource(data=data)
        source = ColumnDataSource(data=dict(x=[], u=[]))
        source.data = source.from_df(data )#[['x', 'u']])
        source.add(data.index, 'index')

        # add a circle renderer with a size, color, and alpha
        p.circle(x='index', y='u', size=2, line_color="navy", fill_color="orange", fill_alpha=0.5, source=source)
        #show(p)

        output_notebook()
        # cf. http://bokeh.pydata.org/en/0.10.0/docs/user_guide/embed.html
        self.Display(HTML(file_html(p, CDN, "my plot")))  # show the results

        # using JS requires jupyter widgets extension
        #script, div = components(p)
        #div = notebook_div(p)
        #self.Display(Javascript(script + div))  # show the results


    def display_plt(self):
        # plt.ion()

        # plot = plt.plot([3, 8, 2, 5, 1])
        #self.Display(plot)
        # plt.show() #TODO find out why there is no comm and interactive shell - and if it should be there

        # cf. http://ipython-books.github.io/16-creating-a-simple-kernel-for-jupyter/
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.plot([3, 8, 2, 5, 1])

        # We create a PNG out of this plot.
        png = _to_png(fig)

        # and send it along as rich content
        self.richcontent = dict()

        # We prepare the response with our rich data (the plot).
        self.richcontent['source'] = 'kernel'

        # This dictionary may contain different MIME representations of the output.
        self.richcontent['data'] = {
                                        'image/png': png  #TODO error: Notebook JSON is invalid: [{'image/png': ...
                                    },
        # We can specify the image size in the metadata field.
        self.richcontent['metadata'] = {
                                            'image/png': {
                                                'width': 600,
                                                'height': 400
                                            }
                                        }
        self.poutput("image!")

if __name__ == '__main__':
    # from ipykernel.kernelapp import IPKernelApp
    # IPKernelApp.launch_instance(kernel_class=Interview)
    Interview.run_as_main()