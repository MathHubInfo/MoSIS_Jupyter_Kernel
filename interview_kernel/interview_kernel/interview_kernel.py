#!/usr/bin/env python3

# http://cmd2.readthedocs.io
#import cmd2 as cmd
from ipykernel.kernelbase import Kernel
from ipykernel.comm import CommManager

from metakernel import MetaKernel

# http://mattoc.com/python-yes-no-prompt-cli.html
# https://github.com/phfaist/pylatexenc for directly converting Latex commands to unicode
from pylatexenc.latex2text import LatexNodes2Text
import getpass
from pde_state_machine import *



# This "main class" is two things: a REPL loop, by subclassing the cmd2 Cmd class
# and a state machine as given by the pytransitions package
class Interview(MetaKernel):
    implementation = 'Interview'
    implementation_version = '1.0'
    language = 'no-op'
    language_version = '0.1'
    language_info = {
        'name': 'Any text',
        'mimetype': 'text/plain',
        'file_extension': '.txt',
    }
    banner = "Interview kernel\n\n" \
             "Hello, " + getpass.getuser() + "! I am " + "TheInterview" + ", your partial differential equations and simulations expert. " \
                                                                           "Let's set up a simulation together.\n" \
             "Please enter anything to start the interview."
    #                                                                       "How many dimensions does your model have?" #TODO this never shows in the notebook

    def __init__(self, **kwargs):

        self.state_machine = PDE_States(self.poutput, self.update_prompt, self.please_prompt)

        # call superclass constructor
        super(Interview, self).__init__(**kwargs)
        # cf.  https://github.com/ipython/ipykernel/blob/7d91110f8f471dbdd3ea65099abcb96a99179557/ipykernel/ipkernel.py
        # self.comm_manager = CommManager(parent=self, kernel=self)

        from IPython import get_ipython
        from metakernel import register_ipython_magics
        # register_ipython_magics()

        self.update_prompt()
        self.poutstring = ""# to collect string output to send
        self.outstream_name = 'stdout'

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
                self.state_input_handling(arg)

        if not silent:
            stream_content = {'name': self.outstream_name, 'text': self.poutstring}
            self.send_response(self.iopub_socket, 'stream', stream_content)

        self.poutstring = ""
        self.outstream_name = 'stdout'

        return {'status': 'ok',
                # The base class increments the execution count
                'execution_count': self.execution_count,
                'payload': [],
                'user_expressions': {},
                }

    def state_input_handling(self, arg):
        """The standard input handling, depending on which state we are in"""
        # pythonic switch-case, cf. https://bytebaker.com/2008/11/03/switch-case-statement-in-python/
        try:
            self.state_machine.stateDependentInputHandling[self.state_machine.state](arg)
        except Exception as error:
            #self.state_machine.exaout.create_output(self.simdata)
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
        self.trigger('last_state')

    def help_undo(self):
        self.poutput('\n'.join(['undo',
                                'Go back to the last question',
                                ]))

    def update_prompt(self):
        self.prompt = "(" + self.state_machine.state + ")" #TODO

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


if __name__ == '__main__':
    # from ipykernel.kernelapp import IPKernelApp
    # IPKernelApp.launch_instance(kernel_class=Interview)
    Interview.run_as_main()