#!/usr/bin/env python3

# http://cmd2.readthedocs.io
import cmd2 as cmd
# http://mattoc.com/python-yes-no-prompt-cli.html
from distutils.util import strtobool
# https://github.com/phfaist/pylatexenc for directly converting Latex commands to unicode
from pylatexenc.latex2text import LatexNodes2Text
import pyparsing as pp

from pde_state_machine import *

# This "main class" is two things: a REPL loop, by subclassing the cmd2 Cmd class
# and a state machine as given by the pytransitions package
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
        self.intro = "Hello, " + self.username + "! I am " + self.myname + ", your partial differential equations and simulations expert. " \
                                                                           "Let's set up a simulation together.\n" \
                                                                           "How many dimensions does your model have?"
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

    def please_prompt(self, query, if_yes, if_no=None):
        self.poutput(str(query) + " [y/n]? ")
        self.state_machine.prompted = True
        self.state_machine.if_yes = if_yes
        self.state_machine.if_no = if_no

    def prompt_input_handling(self, arg):
        """ If we asked for a yes-no answer, execute what was specified in please_prompt.
        return true if the input was handled here, and false if not."""
        if self.state_machine.prompted:
            if arg == "":
                self.poutput("Yes")
                ret = True
            else:
                try:
                    ret = strtobool(str(arg).strip().lower())
                except ValueError:
                    # or use as input to callback an input processing fcn..?
                    self.poutput("Please answer with Y/n")
                    return True
            self.state_machine.prompted = False
            if ret:
                self.state_machine.if_yes()
            elif self.state_machine.if_no is not None:
                self.state_machine.if_no()
            else:
                return False
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


if __name__ == '__main__':
    Interview().cmdloop()
