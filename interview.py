#!/usr/bin/env python3

import sys
import errno
import traceback
# http://cmd2.readthedocs.io
import cmd2 as cmd
# https://github.com/pytransitions/transitions
from transitions import Machine, State
from collections import OrderedDict
# strings:
# http://mattoc.com/python-yes-no-prompt-cli.html
from distutils.util import strtobool
from pathlib import Path
# https://github.com/phfaist/pylatexenc for directly converting Latex commands to unicode
from pylatexenc.latex2text import LatexNodes2Text
import pyparsing as pp
from lxml import etree
import re

from exaoutput import ExaOutput
from mmtinterface import *


# This "main class" is two things: a REPL loop, by subclassing the cmd2 Cmd class
# and a state machine as given by the pytransitions package
class Interview(cmd.Cmd):

    def __init__(self, *args, **kwargs):
        # just act like we were getting the right replies from MMT
        self.cheating = True
        # initialize legal characters for cmd
        self.legalChars = u'!#$%.:;?@_-<>' + pp.printables + pp.alphas8bit + pp.punc8bit
        # TODO why does "<" not show?
        # allow all useful unicode characters to be used, and some more
        for i in range(0x20, 0x2E7F):
            self.legalChars += chr(i)

        # call cmd constructor
        super(Interview, self).__init__(*args, **kwargs)

        # Initialize a state machine
        states = [
            # State('greeting'),
            State('dimensions', on_enter=['dimensions_begin']),
            State('domain', on_enter=['domain_begin'], on_exit=['domain_exit']),
            State('unknowns', on_enter=['unknowns_begin'], on_exit=['unknowns_exit']),
            State('parameters', on_enter=['parameters_begin'], on_exit=['parameters_exit']),
            State('pdes', on_enter=['pdes_begin'], on_exit=['pdes_exit']),
            'pdes',
            'bcs',
            'sim'
        ]
        states.reverse()
        self.machine = Machine(model=self, states=states, initial=states[-1], after_state_change='update_prompt')
        # this is why we were reverting the states => can always go back
        self.machine.add_ordered_transitions(
            trigger='last_state')  # TODO do something to avoid going back from the first state
        # self.to_dimensions()
        # self.machine.add_transition(trigger='greeting_over', source='greeting', dest='dimensions')
        self.machine.add_transition(trigger='dimensions_parsed', source='dimensions', dest='domain',
                                    before='print_empty_line')
        self.machine.add_transition(trigger='domain_parsed', source='domain', dest='unknowns',
                                    before='print_empty_line')
        self.machine.add_transition(trigger='unknowns_parsed', source='unknowns', dest='parameters',
                                    after='print_empty_line')
        self.machine.add_transition(trigger='parameters_parsed', source='parameters', dest='pdes',
                                    after='print_empty_line')
        self.machine.add_transition(trigger='pdes_parsed', source='pdes', dest='bcs', before='print_empty_line')
        self.machine.add_transition(trigger='bcs_parsed', source='bcs', dest='sim', before='print_empty_line')

        # Initialize cmd member variables
        self.myname = 'James'
        self.username = 'user'
        self.intro = "Hello, " + self.username + "! I am " + self.myname + ", your partial differential equations and simulations expert. " \
                                                                           "Let's set up a simulation together.\n" \
                                                                           "How many dimensions would you like to simulate?"

        # define what happens when input is received in a certain state
        self.stateDependentInputHandling = {
            'dimensions': self.dimensions_handle_input,
            'domain': self.domain_handle_input,
            'unknowns': self.unknowns_handle_input,
            'parameters': self.parameters_handle_input,
            'pdes': self.pdes_handle_input,  # TODO
            'bcs': None,
            'sim': None,
        }

        self.mmtinterface = MMTInterface()

        # for ladder-like views
        self.viewfrom = OrderedDict([
            ('domain', "GeneralDomains"),
            ('unknowns', "Unknown"),
            ('parameters', "Parameter"),
            ('pdes', "PDE"),
            ('bcs', "BCsRequired"),
        ])
        # to include all the necessary theories every time
        self.bgthys = OrderedDict([
            ('domain', ["SimpleDomains", "http://mathhub.info/MitM/smglom/arithmetics?realarith"]),
            # new: RealArithmetics
            ('unknowns', ["http://mathhub.info/MitM/Foundation?Strings", "ephdomain",
                          "http://mathhub.info/MitM/smglom/calculus?higherderivative"]),
            ('parameters', ["http://mathhub.info/MitM/smglom/arithmetics?realarith", "ephdomain"]),
            ('pdes', ["DifferentialOperators"]),
            ('bcs',
             ["BCTypes", "ephUnknown", "ephPDE", "linearity", "http://mathhub.info/MitM/smglom/arithmetics?realarith"]),
        ])

        # the things we'd like to find out
        self.simdata = {
            "num_dimensions": None,
            "domain": {
                "name": None,
                "theoryname": None,
                # "viewname" : None,
                "axes": OrderedDict(),
                "from": None,
                "to": None,
            },
            "unknowns": OrderedDict(),
            "parameters": {},
            "pdes": {
 #               "theoryname": None,
                "pdes": [],
            },
            "bcs": None,
            "sim_type": None,
        }

        axes = OrderedDict([
            ("x_1", "[0;1]"),
        ])
        self.examplesimdata = {
            "num_dimensions": 1,
            "domain": {
                "name": "Ω",
                "theoryname": "Omega",
                "axes": axes,  # names and intervals
                "from": "[ 0 ]",
                "to": "[ 1 ]",
            },
            "unknowns": {  # names and theorynames #TODO OrderedDict
                "u": {
                    "theoryname": "u",
                    "string": "u : Ω → ℝ",
                },
            },
            "parameters": {  # names and theorynames
                "μ": {
                    "theoryname": "mu",
                    "string": "μ : ℝ = 1",
                },
                "f": {
                    "theoryname": "f",
                    "string": "f : Ω → ℝ = [x] x ⋅ x",
                },
            },
            "pdes": {
                "pdes": [
                    {  # this is more of a wish list...
                        "theoryname": "pde1",
                        "string": "μ ∆u = f(x_1)",  # TODO
                        "expanded": "μ d²/dx_1² u = f(x_1)",
                        "type": "elliptic",
                        "linear": True,
                        "order_in_unknown": {
                            "u": 2,
                        },
                    },
                ],
            },
            "bcs": [
                {
                    "theoryname": "bc1",
                    "type": "Dirichlet",
                    "string": "u (0) = x_1**2",
                    "on": "[0]",
                },
                {
                    "theoryname": "bc2",
                    "type": "Dirichlet",
                    "string": "u (1) = x_1**2",
                    "on": "[1]",
                },
            ],
            "sim_type": "FD",
        }

        self.exaout = ExaOutput()
        # self.greeting()
        self.update_prompt()

    ##### for state dimensions
    def dimensions_begin(self):
        self.poutput("How many dimensions would you like to simulate?")
        self.poutput("I am just assuming it's 1, since that is all we can currently handle.")  # TODO
        self.simdata["num_dimensions"] = 1
        self.dimensions_parsed()

    def dimensions_handle_input(self, userstring):
        try:
            numdim = int(userstring)
        except ValueError:
            self.poutput("Please enter a number.")
            return
        if numdim < 1:
            self.obviously_stupid_input()
            self.dimensions_begin()
        elif numdim == 1:  # or self.numdim == 2:
            self.simdata["num_dimensions"] = numdim
            self.dimensions_parsed()
        else:
            self.poutput(
                "Sorry, cannot handle " + str(self.numdim) + " dimensions as of now. Please try less than that.")

    ##### for state domain
    def domain_begin(self):
        self.poutput("What is the domain you would like to simulate for?     Ω : type ❘ = [?;?]")
        self.poutput("By the way, you can always try and use LaTeX-type input.")
        self.simdata[self.state]["axes"] = OrderedDict()
        self.domain_mmt_preamble()

    def domain_handle_input(self, userstring):
        domain_name = re.split('\W+', userstring, 1)[0]
        parsestring = userstring
        try:
            mmtparsed = self.mmtinterface.mmt_new_decl(domain_name, self.simdata[self.state]["theoryname"], parsestring)
        except MMTServerError as error:
            print(error.args)
        mmtparsed = (mmtparsed if not self.cheating else True)
        if mmtparsed:
            try:
                mmtreply = self.mmtinterface.query_for(self.simdata[self.state]["theoryname"])
            except MMTServerError as error:
                print(error.args)
            mmtparsed = (mmtreply.ok)  # if not self.cheating else True)
        if mmtparsed:
            # (ok, root) = self.mmtinterface.query_for(self.simdata[self.state]["theoryname"])
            self.simdata[self.state]["name"] = domain_name
            (fro, to) = mmtreply.getIntervalBoundaries(mmtreply, domain_name) if not self.cheating else ("0.", "1.")
            self.simdata[self.state]["axes"]["x_1"] = "[" + fro + ";" + to + "]"
            # self.poutput(self.simdata[self.state]["axes"]["x_1"])
            (self.simdata[self.state]["from"], self.simdata[self.state]["to"]) = ("[ " + fro + " ]", "[ " + to + " ]")
            self.trigger('domain_parsed')
        else:
            self.please_repeat()

    def domain_exit(self):
        self.domain_mmt_postamble()

    def domain_mmt_preamble(self):
        # set the current MMT theoryname for parsing the input TODO use right dimension
        self.simdata[self.state]["theoryname"] = "ephdomain"
        # self.simdata[self.state]["viewname"] = self.construct_current_view_name(self.simdata[self.state])
        self.new_theory(self.simdata[self.state]["theoryname"])
        # (ok, root) = self.mmtinterface.query_for(self.simdata[self.state]["theoryname"])

    def domain_mmt_postamble(self):
        subdict = self.simdata[self.state]
        if not self.cheating:
            self.mmtinterface.mmt_new_decl('mydomainpred', subdict["theoryname"],
                                           "myDomainPred = " + subdict["name"] + ".interval_pred")
            self.mmtinterface.mmt_new_decl('mydomain', subdict["theoryname"],
                                           "myDomain = intervalType " + subdict["name"])
            # and a view to understand our interval as a domain -- view ephDomainAsDomain : ?GeneralDomains → ?ephDomain =
            self.new_view(subdict)
            self.mmtinterface.mmt_new_decl('Vecspace', subdict["viewname"],
                                           "Vecspace = real_lit")  # TODO adjust for higher dimensions
            self.mmtinterface.mmt_new_decl('DomainPred', subdict["viewname"], "DomainPred = " + subdict[
                "name"] + ".interval_pred")  # the . is unbound, apparently...

    ##### for state unknowns
    def unknowns_begin(self):
        self.poutput("Which variable(s) are you looking for?   u : " + self.simdata["domain"][
            "name"] + " → ℝ ?")  # problem: omega not a type (yet), need to have it look like one
        self.simdata["unknowns"] = OrderedDict()

    def unknowns_handle_input(self, userstring):
        unknown_name = re.split('\W+', userstring, 1)[0]
        # replace interval with domain
        parsestring = (
            userstring.replace(self.simdata["domain"]["name"],
                               "pred myDomainPred") if not self.cheating else userstring)
        # print(parsestring)
        # print('type: ' + str(self.get_last_type(self.get_type(parsestring))))
        self.simdata["unknowns"][unknown_name] = {
            "theoryname": str("" + unknown_name),
            # "viewname" : self.construct_current_view_name(self.simdata[self.state]),
            "string": parsestring,
            "type": self.get_type(parsestring),
        }
        self.simdata["unknowns"][unknown_name]["viewname"] = self.construct_current_view_name(
            self.simdata["unknowns"][unknown_name])
        subdict = self.simdata["unknowns"][unknown_name]
        # create mmt theory with includes
        once = self.new_theory(subdict["theoryname"])
        self.include_in(subdict["theoryname"], self.simdata["domain"]["theoryname"])
        # add unknown's type as constant
        twice = self.mmtinterface.mmt_new_decl(unknown_name, subdict["theoryname"],
                                               "myUnkType = " + self.simdata["unknowns"][unknown_name][
                                                   "type"])  # hacky!
        twice = (self.mmtinterface.mmt_new_decl('diffable', subdict["theoryname"],
                                                "anyuwillbediffable : {u : myUnkType} ⊦ twodiff u ") if not self.cheating else twice)
        mmtparsed = twice.ok
        # add view
        if mmtparsed:
            mmtparsed = self.new_view(subdict)
            mmtparsed = mmtparsed and self.mmtinterface.mmt_new_decl("codomain", subdict["viewname"],
                                                                     "ucodomain = ℝ").ok  # TODO
            mmtparsed = mmtparsed and (self.mmtinterface.mmt_new_decl("unktype", subdict["viewname"],
                                                                     "unknowntype = myUnkType").ok if not self.cheating else True)

        if mmtparsed:
            self.poutput("Ok, " + userstring)
            if self.please_prompt("Are these all the unknowns?"):
                self.trigger('unknowns_parsed')
        else:
            del self.simdata["unknowns"][unknown_name]
            # need to delete mmt ephemeral theory too
            self.please_repeat()
        # print(str(self.simdata))

    def unknowns_exit(self):
        for unknown in self.simdata["unknowns"]:
            self.poutput(self.simdata["unknowns"][unknown]["string"])

    ##### for state parameters
    def parameters_begin(self):
        self.poutput(
            "Would you like to name additional parameters like constants or functions (that are independent of your unknowns)?  c : ℝ = ? or f : Ω → ℝ = ?")  # ℝ
        self.simdata["parameters"] = {}

    def parameters_handle_input(self, userstring):
        # self.poutput ("parameterinput "+ userstring)
        if self.means_no(userstring):
            self.trigger('parameters_parsed')
            return

        parameter_name = re.split('\W+', userstring, 1)[0]

        self.simdata["parameters"][parameter_name] = {
            "theoryname": "" + parameter_name,
            "string": userstring,
            "type": self.get_type(userstring),
        }
        subdict = self.simdata["parameters"][parameter_name]
        # create mmt theory
        mmtparsed = self.new_theory(subdict["theoryname"]).ok

        if mmtparsed and not self.cheating: #theory parameter seems to not exist
            mmtparsed = self.new_view(subdict)
            mmtparsed = mmtparsed and self.mmtinterface.mmt_new_decl("ptype", subdict["viewname"],
                                                                 "paramtype = " + subdict["type"]).ok  # TODO
        #TODO create view
        if mmtparsed:
            # self.poutput ("Ok, " +  userstring)
            if self.please_prompt("Are these all the parameters?"):
                self.trigger('parameters_parsed')
        else:
            del self.simdata["parameters"][parameter_name]
            self.please_repeat()
        # print(str(self.simdata))

    def parameters_exit(self):
        # print(str(self.simdata["parameters"]))
        for parameter in self.simdata["parameters"]:
            self.poutput(self.simdata["parameters"][parameter]["string"])

    ##### for state pdes
    def pdes_begin(self):
        self.poutput("Let's get to your partial differential equation(s). What do they look like?")
        self.simdata["pdes"]["pdes"] = []

    def pdes_handle_input(self, userstring):
        # create mmt theory
        self.simdata["pdes"]["theoryname"] = "ephpde"
        self.new_theory(self.simdata["pdes"]["theoryname"])
        # include unknowns, parameters, differential operators
        #inc = self.include_in(self.simdata["pdes"]["theoryname"], cuboidURI)
        # TODO send as declaration to mmt
        # TODO make view

        mmtparsed = True
        mmtresult = userstring
        # TODO store result
        # TODO use symbolic computation to order into LHS and RHS
        # TODO send as declaration to mmt
        # TODO make view
        # TODO query number of effective pdes and unknowns from mmt
        if mmtparsed:
            numpdesgiven = 1
            # => can assume each to be ==1 for now
            self.poutput("Ok, " + mmtresult)
            if numpdesgiven == len(self.simdata["unknowns"]):
                self.trigger('pdes_parsed')
            elif numpdesgiven > len(self.simdata["unknowns"]):
                self.poutput("now that's too many PDEs. Please go back and add more unknowns.")
        else:
            self.please_repeat()

    def pdes_exit(self):
        self.poutput("These are all the PDEs needed.")

    ### functions for user interaction
    def please_repeat(self, moreinfo=None):
        append = ""
        if moreinfo:
            append = "\nDetails: " + moreinfo
        self.poutput("I did not catch that. Could you please rephrase?" + append)

    def please_prompt(self, query):
        self.poutput(query + " [Y/n]? ")
        val = input()
        if val == "":
            return True
        try:
            ret = strtobool(val)
        except ValueError:
            # or use as input to callback an input processing fcn..?
            self.poutput("Please answer with Y/n")
            return self.please_prompt(query)
        return ret

    def means_no(self, answer):
        try:
            ret = strtobool(answer)
            if (ret == False):
                return True
        except ValueError:
            return False
        return False

    def obviously_stupid_input(self):
        self.poutput("Trying to be funny, huh?")

    # string processing
    def has_equals(self, string):
        if string.find("=") > -1:
            return True
        return False

    def has_colon(self, string):
        if string.find(":") > -1:
            return True
        return False

    def eq_to_doteq(self, string):
        return string.replace("=", "≐")

    ### mmt input helper functions
    def include_in(self, in_which_theory, what):
        return self.mmtinterface.mmt_new_decl("inc", in_which_theory, "include " + self.assert_questionmark(what))

    def include_bgthys(self, in_which_theory):
        ok = True
        for bgthy in self.bgthys[self.state]:
            ok = ok and self.include_in(in_which_theory, bgthy)
        return ok

    def assert_questionmark(self, what):
        qmidx = what.find("?")
        if qmidx < 0:
            return "?" + what
        else:
            return what

    def new_theory(self, thyname):
        self.mmtinterface.mmt_new_theory(thyname)
        # (ok, root) = self.mmtinterface.query_for(self.simdata[self.state]["theoryname"])
        return self.include_bgthys(thyname)

    def new_view(self, dictentry):
        dictentry["viewname"] = self.construct_current_view_name(dictentry)
        # self.poutput("new view: "+dictentry["viewname"])
        ok = self.mmtinterface.mmt_new_view(dictentry["viewname"], self.viewfrom[self.state], dictentry["theoryname"])
        # recursively look for all views already done and include them
        for viewstring in self.get_recursively(self.simdata, "viewname"):
            if (dictentry["viewname"] != viewstring) and ok:
                ok = self.include_in(dictentry["viewname"], "?" + re.split('AS', viewstring)[-1] + " = " + "?" + viewstring)
        return ok

    def construct_current_view_name(self, dictentry):
        return self.construct_view_name(dictentry, self.state)

    def construct_view_name(self, dictentry, state):
        return dictentry["theoryname"] + "AS" + (self.viewfrom[state])

    # cf. https://stackoverflow.com/questions/14962485/finding-a-key-recursively-in-a-dictionary
    def get_recursively(self, search_dict, field):
        """
        Takes a dict with nested lists and dicts, and searches all dicts for a key of the field provided.
        """
        fields_found = []
        for key, value in search_dict.items():
            if key == field:
                fields_found.append(value)
            elif isinstance(value, dict):
                results = self.get_recursively(value, field)
                for result in results:
                    fields_found.append(result)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        more_results = self.get_recursively(item, field)
                        for another_result in more_results:
                            fields_found.append(another_result)
        return fields_found

    def insert_type(self, string, whichtype):
        eqidx = string.find("=")
        if eqidx < 0:
            raise Exception
        if not self.has_colon(string):
            # print('has no colon ' + equidx)
            return string[:eqidx] + " : " + whichtype + " ❘ " + string[eqidx:]
        return string[:eqidx] + " ❘ " + string[eqidx:]

    def get_type(self, string):
        colidx = string.find(":")
        eqidx = string.find("=")
        if eqidx > -1:
            return string[colidx + 1:eqidx]
        return string[colidx + 1:]

    def insert_before_def(self, string, insertstring):
        eqidx = string.find("=")
        if eqidx < 0:
            raise Exception
        return string[:eqidx + 1] + " " + insertstring + " " + string[eqidx + 1:]

    def get_first_word(self, string):
        return re.split('\W+', string, 1)[0]

    def get_last_type(self, string):
        return re.split('[→ \s]', string)[-1]

    def print_empty_line(self):
        self.poutput("\n")

    ############# input processing if not explain or undo
    def default(self, line):
        raw = line.parsed['raw']
        arg = LatexNodes2Text().latex_to_text(raw)
        # self.poutput ('default({0})'.format(arg))
        # pythonic switch-case, cf. https://bytebaker.com/2008/11/03/switch-case-statement-in-python/
        try:
            # self.poutput("You entered "+arg)
            self.stateDependentInputHandling[self.state](arg)
        except:
            self.exaout.create_output(self.examplesimdata)
            raise
            # self.perror('State machine broken: '+self.state)

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
        self.prompt = "(" + self.state + ")"

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
                'parameters': ['f : Ω → ℝ = [x] x ⋅ x'],
                'pdes': ['∆u = f(x_1)'],
                'bcs': ['u (0) = 0'],  # ,'u (1) = x_1**2'],
                'sim': ['FD'],
            }
            return self.stateDependentDefaultInput[self.state]
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
