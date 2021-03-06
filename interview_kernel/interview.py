#!/usr/bin/env python3

# http://cmd2.readthedocs.io
import cmd2 as cmd
# http://mattoc.com/python-yes-no-prompt-cli.html
from distutils.util import strtobool
# https://github.com/phfaist/pylatexenc for directly converting Latex commands to unicode
from pylatexenc.latex2text import LatexNodes2Text
import pyparsing as pp

from pde_state_machine import *

import matplotlib
matplotlib.use('nbagg')
import matplotlib.pyplot as plt
from bokeh.io import output_notebook, show, export_svgs
from bokeh.plotting import figure
from tempfile import NamedTemporaryFile

# This "main class" is a REPL loop, by subclassing the cmd2 Cmd class
class Interview(cmd.Cmd):
    def __init__(self, *args, **kwargs):

        self.state_machine = PDE_States(self.poutput, self.update_prompt, self.please_prompt)

        # initialize legal characters for cmd
        self.legalChars = u'!#$%.:;?@_-<>' + pp.printables + pp.alphas8bit + pp.punc8bit
        # TODO why does "<" not show?
        # allow all useful unicode characters to be used, and some more
        for i in range(0x20, 0x2E7F):
            self.legalChars += chr(i)

        # call cmd constructor
        super(Interview, self).__init__(*args, **kwargs)

        # Initialize cmd member variables
        self.myname = 'TheInterview'
        self.username = 'user'
        self.intro = "Hello, " + self.username + "! I am " + self.myname + \
                     ", your partial differential equations and simulations expert. " \
                     "Let's set up a simulation together.\n" \
                     "Please enter anything to start the interview."
        # self.greeting()
        self.update_prompt()


    #### functions for user interaction

    def obviously_stupid_input(self):
        self.poutput("Trying to be funny, huh?")

    ############# input processing if not explain or undo
    def default(self, line):
        raw = line.parsed['raw']
        arg = LatexNodes2Text().latex_to_text(raw)
        # pythonic switch-case, cf. https://bytebaker.com/2008/11/03/switch-case-statement-in-python/

        if not self.keyword_handling(arg):
            if not self.prompt_input_handling(arg):
                self.state_input_handling(arg)

    def state_input_handling(self, arg):
        """The standard input handling, depending on which state we are in"""
        # pythonic switch-case, cf. https://bytebaker.com/2008/11/03/switch-case-statement-in-python/
        try:
            self.state_machine.stateDependentInputHandling[self.state_machine.state](arg)
        except Exception as error:
            #self.state_machine.exaout.create_output(self.state_machine.simdata)
            raise

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
        return False

    def help_explain(self):
        self.poutput('\n'.join(['explain [expression]',
                                'explain the expression given or the theory currently used',
                                ]))

    # called when user types 'undo'
    def do_undo(self, expression):
        "Go back to the last question"
        self.trigger('last_state')

    def help_undo(self):
        self.poutput('\n'.join(['undo',
                                'Go back to the last question',
                                ]))

    def update_prompt(self):
        self.prompt = "(" + self.state_machine.state + ")"

    # tab completion for empty lines
    def completenames(self, text, line, begidx, endidx):
        """Override of cmd2 method which completes command names both for command completion and help."""
        command = text
        if self.case_insensitive:
            command = text.lower()
        if not command:
            # define the "default" input for the different states we can be in
            self.stateDependentDefaultInput = {
                'dimensions': '1',
                'domain': ['Ω = [ 0 ; 1 ]'],
                'unknowns': ['u : Ω → ℝ'],
                'parameters': ['f :  ℝ → ℝ = [x: ℝ] x '],  # ['f : Ω → ℝ = [x:Ω] x ⋅ x'],
                'pdes': ['∆u = f(x_1)'],
                'bcs': ['u (0) = 0'],  # ,'u (1) = x_1**2'],
                'sim': ['FD'],
            }
            return self.stateDependentDefaultInput[self.state_machine.state]
        else:
            # Call super class method.  Need to do it this way for Python 2 and 3 compatibility
            cmd_completion = cmd.Cmd.completenames(self, command)

            # If we are completing the initial command name and get exactly 1 result and are at end of line, add a space
            if begidx == 0 and len(cmd_completion) == 1 and endidx == len(line):
                cmd_completion[0] += ' '
            return cmd_completion

    def greeting(self):  # TODO make work in proper order
        self.poutput(
            "Hello, " + self.username + "! I am " + self.myname + ", your partial differential equations and simulations expert. " \
                                                                  "Let's set up a simulation together.\n")
        self.trigger("greeting_over")

    def do_plt(self, userstring):
        plt.ion()

        plot = plt.plot([3, 8, 2, 5, 1])
        #self.Display(plot)
        plt.show() #TODO find out why there is no comm and interactive shell - and if it should be there

        # cf. http://ipython-books.github.io/16-creating-a-simple-kernel-for-jupyter/
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.plot([3, 8, 2, 5, 1])

        # We create a PNG out of this plot.
        png = _to_png(fig)

        with open('png.png', 'w') as f:
            f.write(png)

        # and send it along as rich content
        self.richcontent = dict()

        # We prepare the response with our rich data (the plot).
        self.richcontent['source'] = 'kernel'

        # This dictionary may contain different MIME representations of the output.
        self.richcontent['data'] = {
                                       'image/png': png  # TODO error: Notebook JSON is invalid: [{'image/png': ...
                                   },
        # We can specify the image size in the metadata field.
        self.richcontent['metadata'] = {
            'image/png': {
                'width': 600,
                'height': 400
            }
        }
        self.poutput("image!")

    # cf. nbviewer.jupyter.org/github/bokeh/bokeh-notebooks/blob/master/tutorial/01 - Basic Plotting.ipynb
    def do_bokeh(self, userstring):
        # create a new plot with default tools, using figure
        p = figure(plot_width=400, plot_height=400)

        # add a circle renderer with a size, color, and alpha
        p.circle([1, 2, 3, 4, 5], [6, 7, 2, 4, 5], size=15, line_color="navy", fill_color="orange", fill_alpha=0.5)
        show(p)
        t = NamedTemporaryFile(suffix="svg")
        p.output_backend = "svg"
        export_svgs(p, filename=t.name)
        svg = open(t.name).buffer

        # and send it along as rich content
        self.richcontent = dict()

        # We prepare the response with our rich data (the plot).
        self.richcontent['source'] = 'kernel'

        # This dictionary may contain different MIME representations of the output.
        self.richcontent['data'] = {
                                       'image/svg': svg
                                   },
        # We can specify the image size in the metadata field.
        self.richcontent['metadata'] = {
            'image/svg': {
                'width': 600,
                'height': 400
            }
        }

if __name__ == '__main__':
    Interview().cmdloop()
