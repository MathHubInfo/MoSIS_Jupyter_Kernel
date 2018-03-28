#!/usr/bin/env python3

# https://github.com/pytransitions/transitions
from transitions import Machine, State
from collections import OrderedDict

import getpass
import re

import string_handling
from exaoutput import ExaOutput, ExaRunner
from mmtinterface import *

from bokeh.io import output_notebook, show, export_svgs
from bokeh.plotting import figure
from bokeh.resources import CDN
from bokeh.embed import file_html, components#, notebook_div
from bokeh.models import ColumnDataSource

class InterviewError(Exception):
    """Errors that occur during the course of the interview and are not due to mmt server errors"""

    def __init__(self, err):
        self.error = err
        super(InterviewError, self).__init__("Interview error: " + str(self.error))


class CriticalSubdict():
    def __init__(self, subdict, output_function=print, outermost=True):
        """The sub-part of a dictionary that needs to be restored if something goes wrong -
        To be used in with-statements.
        Catches errors only if it is the outermost one"""
        self.subdict = subdict
        self.initial_subdict = self.subdict.copy()
        self.output_function = output_function
        self.outermost = outermost

    def __enter__(self):
        return self.subdict

    def __exit__(self, type, value, traceback):
        if type is not None:
            # restore the initial state
            self.subdict.clear()
            for key in self.initial_subdict:
                self.subdict[key] = self.initial_subdict[key]
            # handling: give feedback, only if our own error, and the outermost subdict
            if isinstance(value, MMTServerError) and self.outermost:
                self.please_repeat(value.args[0], value.longerr)
                return True
            elif isinstance(value, InterviewError) and self.outermost:
                self.please_repeat(value.args[0])
                return True
            else:
                return False
        return True

    def please_repeat(self, moreinfo=None, evenmoreinfo=None):
        append = ""
        if moreinfo:
            append = "\nDetails: " + moreinfo
        if evenmoreinfo:
            append += ". " + evenmoreinfo
        self.output_function("I did not catch that. Could you please rephrase?" + append, 'stderr')


class PDE_States:
    """Just a state machine using pytranisitions that walks our theory graph and creates ephemeral theories and views"""

    def __init__(self, output_function, after_state_change_function, prompt_function, display_html_function=None):
        # just act like we were getting the right replies from MMT
        self.cheating = True

        # callback handles
        self.poutput = output_function
        self.please_prompt = prompt_function
        self.display_html = display_html_function

        # Initialize a state machine
        self.states = [
            State('greeting', on_exit=['greeting_exit']),
            State('dimensions', on_enter=['dimensions_begin']),
            State('domain', on_enter=['domain_begin'], on_exit=['domain_exit']),
            State('unknowns', on_enter=['unknowns_begin'], on_exit=['unknowns_exit']),
            State('parameters', on_enter=['parameters_begin'], on_exit=['parameters_exit']),
            State('pdes', on_enter=['pdes_begin'], on_exit=['pdes_exit']),
            State('bcs', on_enter=['bcs_begin'], on_exit=['bcs_exit']),
            State('props', on_enter=['props_begin'], on_exit=['props_exit']),
            State('sim', on_enter=['sim_begin'], on_exit=['sim_exit']),
        ]
        self.states.reverse()
        self.machine = Machine(model=self, states=self.states, initial=self.states[-1],
                               after_state_change=after_state_change_function, queued=True)
        # this is why we were reverting the states => can always go back
        self.machine.add_ordered_transitions(
            trigger='last_state')  # TODO do something to avoid going back from the first state
        # self.to_dimensions()
        self.machine.add_transition(trigger='greeting_over', source='greeting', dest='dimensions')
        self.machine.add_transition(trigger='dimensions_parsed', source='dimensions', dest='domain',
                                    before='print_empty_line')
        self.machine.add_transition(trigger='domain_parsed', source='domain', dest='unknowns',
                                    before='print_empty_line')
        self.machine.add_transition(trigger='unknowns_parsed', source='unknowns', dest='parameters')
        self.machine.add_transition(trigger='parameters_parsed', source='parameters', dest='pdes')
        self.machine.add_transition(trigger='pdes_parsed', source='pdes', dest='bcs', before='print_empty_line')
        self.machine.add_transition(trigger='bcs_parsed', source='bcs', dest='props', before='print_empty_line')
        self.machine.add_transition(trigger='props_parsed', source='props', dest='sim', before='print_empty_line')
        self.machine.add_transition(trigger='sim_finished', source='sim', dest='sim', before='print_empty_line')

        # define what happens when input is received in a certain state
        self.stateDependentInputHandling = {
            'greeting': self.greeting_handle_input,
            'dimensions': self.dimensions_handle_input,
            'domain': self.domain_handle_input,
            'unknowns': self.unknowns_handle_input,
            'parameters': self.parameters_handle_input,
            'pdes': self.pdes_handle_input,
            'bcs': self.bcs_handle_input,
            'props': self.props_handle_input,
            'sim': self.sim_handle_input,
        }

        # for ladder-like views
        self.viewfrom = OrderedDict([
            ('domain', "mDomain"),
            ('unknowns', "mUnknown"),
            ('parameters', "mParameter"),
            ('pdes', "mPDE"),
            ('bcs', "mBCsRequired"),
            ('props', "mEllipticLinearDirichletBoundaryValueProblem"),
            ('sim', "mSolvability"),
        ])
        # to include all the necessary theories every time
        self.bgthys = OrderedDict([
            ('domain', ["mInterval", "http://mathhub.info/MitM/smglom/arithmetics?RealArithmetics"]),
            # new: RealArithmetics
            ('unknowns', ["http://mathhub.info/MitM/Foundation?Strings", "ephdomain"]),
                          #"http://mathhub.info/MitM/smglom/calculus?higherderivative"]),
            ('parameters', ["http://mathhub.info/MitM/smglom/arithmetics?RealArithmetics", "ephdomain",
                            "http://mathhub.info/MitM/Foundation?Math"]),
            ('pdes', ["mDifferentialOperators"]),  # +params, unknowns,
            ('bcs',
             ["ephdomain", "mLinearity",
              "http://mathhub.info/MitM/smglom/arithmetics?RealArithmetics"]),  # +params, unknowns, pdes, bctypes
            ('props',
             ["mLinearity",
              "http://mathhub.info/MitM/Foundation?Strings"]),  # +bcs, pde
            ('sim',
             ["http://mathhub.info/MitM/Foundation?Strings"]),  # +props
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
            "parameters": OrderedDict(),
            "pdes": {
                #               "theoryname": None,
                "pdes": [],
            },
            "bcs": {
                "theoryname": None,
                "bcs": None,
            },
            "props": {

            },
            "sim": {
                "type": None,
            },
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
                "from": 0.0,
                "to": 1.0,
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
                    {
                        "theoryname": "pde1",
                        "string": "μ ∆u = f(x)",  # TODO use function arithmetic
                        'lhsstring': 'μ Δu ',
                        'rhsstring': 'f(x)',
                        'op': 'Δ',
                        'lhsparsestring': ' [ anyu : Ω → ℝ ] Δ anyu ',
                        'rhsparsestring': ' [ x : Ω ]  f(x)',
                        # this is more of a wish list... cf https://github.com/UniFormal/MMT/issues/295
                        "expanded": "μ d²/dx_1² u = f(x_1)",
                        "order_in_unknown": {
                            "u": 2,
                        },
                    },
                ],
            },
            "bcs": {
                "theoryname": "ephbcs",
                "bcs": [
                    {
                        "name": "bc1",
                        "type": "Dirichlet",
                        "string": "u (0) = x_1**2",
                        "on": "0",
                    },
                    {
                        "name": "bc2",
                        "type": "Dirichlet",
                        "string": "u (1) = x_1**2",
                        "on": "1",
                    },
                ],
            },
            "props": {
                "theoryname": "ephboundaryvalueproblem",
                "ops": [
                    {
                        "name": "op1",
                        "linear": True,  # or false or unknown
                        "props": ["elliptic"]
                    }
                ]
            },
            "sim": {
                "type": "FD",
            },
        }

        self.testsimdata = {
            'num_dimensions': 1,
            'domain': {'name': 'Ω', 'theoryname': 'ephdomain', 'axes': OrderedDict([('x_1', '[0.0;1.0]')]),
                       'from': 0.0, 'to': 1.0, 'boundary_name': 'Ω', 'viewname': 'ephdomainASmDomain'},
            'unknowns': OrderedDict([('u', {'theoryname': 'u', 'string': 'u : Ω → ℝ', 'type': 'Ω → ℝ', 'codomain': 'ℝ',
                                            'viewname': 'uASmUnknown'})]),
            'parameters': {
                'f': {'theoryname': 'f', 'string': 'f = x', 'parsestring': 'f = [ x : Ω] x', 'type': '{ : Ω } Ω',
                      'viewname': 'fASmParameter'}},
            'pdes': {'pdes': [
                {'theoryname': 'ephpde1', 'string': 'Δu = 0.0', 'lhsstring': 'Δu', 'rhsstring': '0.0',
                 'viewname': 'ephpde1ASmPDE', 'op': 'Δ', 'lhsparsestring': ' [ anyu : Ω → ℝ ] Δ anyu ',
                 'rhsparsestring': ' [ x : Ω ]  0.0'}]},
            'bcs': {'theoryname': 'ephbcs', 'bcs': [
                {'name': 'bc0', 'string': 'u = f', 'lhsstring': 'u ', 'rhsstring': ' f', 'type': ('Dirichlet',),
                 'on': ('x',), 'measure': (2,)}], 'bctypes': {'theoryname': 'uBCTypes'},
                    'viewname': 'ephbcsASmBCsRequired',
                    'measure_given': 2},
            'props': {},
            'sim': {},
        }

        self.exaout = None

        self.mmtinterface = MMTInterface()
        #with MMTInterface() as self.mmtinterface:
        """Variables to signal callbacks depending on yes/no prompts"""
        self.prompted = False
        self.if_yes = None
        self.if_no = None
        self.pass_other = False

    def handle_state_dependent_input(self, userstring):
        """The standard input handling, depending on which state we are in"""
        # pythonic switch-case, cf. https://bytebaker.com/2008/11/03/switch-case-statement-in-python/
        try:
            self.stateDependentInputHandling[self.state](userstring)
        except Exception as error:
            #self.exaout.create_output(self.simdata)
            raise

    def greeting_handle_input(self, userstring):
        self.greeting_over()

    def greeting_exit(self):
        # username = getpass.getuser()
        # self.poutput("Hello, " + username + "! I am TheInterview, your partial differential equations and simulations expert. "
        #              "Let's set up a simulation together.")
        # self.poutput("")
        # self.poutput("To get explanations, enter \"explain <optional keyword>\". ")
        # self.poutput("To see a recap of what we know so far, enter \"recap <optional keyword>\". ")
        # self.poutput("To interactively visualize ther current theory graph, enter \"tgwiev <optional theory name>\". ")
        # self.poutput("Otherwise, you can always try and use LaTeX-type input.")
        # self.poutput("")
        # self.poutput("You can inspect the currently loaded MMT theories under " + self.mmtinterface.serverInstance)
        # self.poutput("")
        # self.poutput("")
        # self.poutput("")
        return

    ##### for state dimensions
    def dimensions_begin(self):
        self.poutput("How many dimensions does your model have?")
        self.print_empty_line()
        self.poutput("I am just assuming it's 1, since that is all we can currently handle.")  # TODO
        self.print_empty_line()
        self.simdata["num_dimensions"] = 1
        self.dimensions_parsed()

    def dimensions_handle_input(self, userstring):
        # reply_diffops = self.mmtinterface.query_for("mDifferentialOperators")
        # self.poutput(reply_diffops.tostring())
        # self.poutput(element_to_string(reply_diffops.getConstant("derivative")))
        # self.poutput(element_to_string(reply_diffops.getConstant("laplace_operator")))
        try:
            numdim = int(userstring)
        except ValueError:
            self.poutput("Please enter a number.")
            return
        if numdim < 1:
            self.obviously_stupid_input()
            ExaOutput(self.testsimdata)
            self.dimensions_begin()
        elif numdim == 1:  # or self.numdim == 2:
            self.simdata["num_dimensions"] = numdim
            self.dimensions_parsed()
        else:
            self.poutput(
                "Sorry, cannot handle " + str(numdim) + " dimensions as of now. Please try less than that.")

    ##### for state domain
    def domain_begin(self):
        self.poutput("What is the domain in your model?     Ω : type ❘ = [?;?], e.g. `\\Omega = [0.0;1.0]`")
        # self.poutput("By the way, you can always try and use LaTeX-type input.")
        self.simdata[self.state]["axes"] = OrderedDict()
        self.domain_mmt_preamble()

    def domain_handle_input(self, userstring):
        domain_name = string_handling.get_first_word(userstring)
        # subdict = self.simdata[self.state]
        with CriticalSubdict(self.simdata[self.state], self.poutput) as subdict:
            parsestring = userstring
            mmtreply = self.mmtinterface.mmt_new_decl(domain_name, subdict["theoryname"], parsestring)
            mmttype = self.mmtinterface.mmt_infer_type(subdict["theoryname"], domain_name)
            if mmttype.inferred_type_to_string() != "type":
                raise InterviewError("This seems to not be a type. It should be!")
            result = self.mmtinterface.query_for(subdict["theoryname"])
            subdict["name"] = domain_name
            (fro, to) = mmtreply.getIntervalBoundaries(result, domain_name)
            subdict["axes"]["x"] = "[" + str(fro) + ";" + str(to) + "]"
            (subdict["from"], subdict["to"]) = (fro, to)

            self.poutput("we will just assume that the variable is called " + string_handling.get_first_key(subdict["axes"]) + " for now.")
            # mmtreply = self.mmtinterface.mmt_new_decl(domain_name, subdict["theoryname"], "x : " + domain_name)
            self.trigger('domain_parsed')

    def domain_exit(self):
        self.domain_mmt_postamble()

    def domain_mmt_preamble(self):
        # set the current MMT theoryname for parsing the input TODO use right dimension
        self.simdata[self.state]["theoryname"] = "ephdomain"
        self.new_theory(self.simdata[self.state]["theoryname"])
        # (ok, root) = self.mmtinterface.query_for(self.simdata[self.state]["theoryname"])

    def domain_mmt_postamble(self):
        with CriticalSubdict(self.simdata[self.state], self.poutput) as subdict:
            subdict["boundary_name"] = subdict["name"]  # todo
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
            else:
                self.new_view(subdict)
                self.mmtinterface.mmt_new_decl('dom', subdict["viewname"],
                                               "domain = " + subdict["name"])
                self.mmtinterface.mmt_new_decl('boun', subdict["viewname"],
                                               "boundary = " + subdict["boundary_name"])

    ##### for state unknowns
    def unknowns_begin(self):
        self.poutput("Which variable(s) are you looking for? / What are the unknowns in your model?  u : " +
                     self.simdata["domain"]["name"] + " → ??,  e.g., u : " + self.simdata["domain"]["name"] + " → ℝ ?")
        self.simdata["unknowns"] = OrderedDict()

    def unknowns_handle_input(self, userstring):
        unknown_name = string_handling.get_first_word(userstring)
        # replace interval with domain
        parsestring = (
            userstring.replace(self.simdata["domain"]["name"],
                               "pred myDomainPred") if not self.cheating else userstring)

        with CriticalSubdict(self.simdata[self.state], self.poutput) as usubdict:
            # create mmt theory with includes
            once = self.new_theory(unknown_name)
            # self.include_in(unknown_name, self.simdata["domain"]["theoryname"])

            # and one to "throw away" to infer the type
            self.new_theory(unknown_name + "_to_go_to_trash")
            test = self.mmtinterface.mmt_new_decl(unknown_name, unknown_name + "_to_go_to_trash",
                                                  parsestring)

            type = self.get_inferred_type(unknown_name + "_to_go_to_trash", unknown_name)
            usubdict[unknown_name] = {
                "theoryname": unknown_name,
                "string": parsestring,
                "type": type,
                "codomain": type.replace(self.simdata["domain"]["name"] + " →", "", 1).strip(),
            }
            with CriticalSubdict(self.simdata["unknowns"][unknown_name], self.poutput, False) as subdict:
                if self.mmtinterface.query_for(unknown_name + "_to_go_to_trash").hasDefinition(unknown_name):
                    raise InterviewError("Unknowns cannot be defined!")
                if not string_handling.type_is_function_from(subdict["type"], self.simdata["domain"]["name"]):
                    raise InterviewError("Unknown should be a function on " + self.simdata["domain"]["name"] + "!")

                # add unknown's type as constant
                twice = self.mmtinterface.mmt_new_decl(unknown_name, subdict["theoryname"],
                                                       "myUnkType = " + subdict["type"])
                twice = (self.mmtinterface.mmt_new_decl('diffable', subdict["theoryname"],
                                                        "anyuwillbediffable : {u : myUnkType} ⊦ twodiff u ") if not self.cheating else twice)
                self.new_view(subdict)
                self.mmtinterface.mmt_new_decl("codomain", subdict["viewname"], "ucodomain = " + subdict["codomain"])
                self.mmtinterface.mmt_new_decl("unktype", subdict["viewname"], "unknowntype = myUnkType")
                self.poutput("Ok, " + userstring)
                # self.please_prompt("Are these all the unknowns?", lambda: self.trigger('unknowns_parsed'), pass_other=True) #TODO
                self.trigger('unknowns_parsed')

    def unknowns_exit(self):
        for unknown in self.simdata["unknowns"]:
            self.poutput(self.simdata["unknowns"][unknown]["string"])
        self.print_empty_line()

    ##### for state parameters
    def parameters_begin(self):
        self.poutput(
            "Would you like to name additional parameters like constants or functions (that are independent of your unknowns)?  c : ℝ = ? or f : Ω → ℝ = ?")  # ℝ
        self.simdata["parameters"] = OrderedDict()

    def parameters_handle_input(self, userstring):
        # self.poutput ("parameterinput "+ userstring)
        if string_handling.means_no(userstring):
            self.trigger('parameters_parsed')
            return

        parameter_name = string_handling.get_first_word(userstring)
        with CriticalSubdict(self.simdata["parameters"], self.poutput) as psubdict:
            psubdict[parameter_name] = {}
            with CriticalSubdict(self.simdata["parameters"][parameter_name], self.poutput, False) as subdict:
                # create mmt theory
                self.new_theory(parameter_name)
                # we might need the other parameters created so far, so use them
                for otherparamentry in string_handling.get_recursively(self.simdata["parameters"], "theoryname"):
                    self.include_in(parameter_name, otherparamentry)

                # sanitize userstring - check if this works for all cases
                parsestring = string_handling.add_ods(userstring)
                if parsestring.startswith(parameter_name + "(") or parsestring.startswith(
                        parameter_name + " ("):  # todo make smarter for more dimensions
                    parsestring = string_handling.remove_apply_brackets(parsestring)
                parsestring = string_handling.functionize(parsestring, self.simdata["domain"]["name"])
                # self.poutput(parsestring)

                # add the quantitiy role for display as MPD
                reply_pconstant = self.mmtinterface.mmt_new_decl("param", parameter_name, parsestring +
                                                                 string_handling.object_delimiter + " role Quantity")
                reply_pconstant = self.mmtinterface.query_for(parameter_name)
                subdict["theoryname"] = parameter_name
                subdict["string"] = userstring
                subdict["parsestring"] = parsestring
                subdict["type"] = self.get_inferred_type(parameter_name, parameter_name)

                # if not reply_pconstant.hasDefinition(parameter_name) and not self.cheating:
                #    InterviewError("Please define this parameter.")

                # create view
                self.new_view(subdict)
                self.mmtinterface.mmt_new_decl("ptype", subdict["viewname"],
                                               "ptype = " + subdict["type"])
                self.mmtinterface.mmt_new_decl("param", subdict["viewname"],
                                               "param = " + parameter_name)
                self.poutput("Ok, " + parsestring)
                self.please_prompt("Would you like to declare more parameters?", None,
                                   lambda: self.trigger('parameters_parsed'), True)

    def parameters_exit(self):
        # print(str(self.simdata["parameters"]))
        for parameter in self.simdata["parameters"]:
            self.poutput(self.simdata["parameters"][parameter]["string"])
        self.print_empty_line()

    ##### for state pdes
    def pdes_begin(self):
        self.poutput(
            "Let's talk about your partial differential equation(s). What do they look like? Δu = 0.0, or laplace_operator Ω ℝ u = f ?")
        self.simdata["pdes"]["pdes"] = []

    def pdes_handle_input(self, userstring):
        with CriticalSubdict(self.simdata["pdes"]["pdes"], self.poutput) as psubdict:
            psubdict.append({})
            with CriticalSubdict(self.simdata["pdes"]["pdes"][-1], self.poutput, False) as subdict:
                subdict["theoryname"] = "ephpde" + str(len(self.simdata["pdes"]["pdes"]))
                # create new theory including all unknowns and parameters
                self.new_theory(subdict["theoryname"])
                for unknownentry in string_handling.get_recursively(self.simdata["unknowns"], "theoryname"):
                    self.include_in(subdict["theoryname"], unknownentry)
                for paramentry in string_handling.get_recursively(self.simdata["parameters"], "theoryname"):
                    self.include_in(subdict["theoryname"], paramentry)

                # TODO use symbolic computation to order into LHS and RHS
                parts = re.split("=", userstring)

                if len(parts) is not 2:
                    raise InterviewError("This does not look like an equation.")

                # store the info
                subdict["string"] = userstring
                subdict["lhsstring"] = parts[0].strip()
                subdict["rhsstring"] = parts[1].strip()
                subdict["rhsstring_expanded"] = self.try_expand(subdict["rhsstring"])  # TODO expand properly

                # to make the left-hand side a function on x, place " [ variablename : domainname ] " in front
                if "x" in parts[0]:
                    parts[0] = " [ x : " + self.simdata["domain"]["name"] + " ] " + parts[0]
                # right-hand side: infer type, make function if not one yet
                if not string_handling.type_is_function_from(self.get_inferred_type(subdict["theoryname"], parts[1]),
                                             self.simdata["domain"]["name"]):
                    parts[1] = " [ x : " + self.simdata["domain"]["name"] + " ] " + parts[1]

                # in lhs replace all unknown names used by more generic ones and add lambda clause in front
                for unkname in string_handling.get_recursively(self.simdata["unknowns"], "theoryname"):
                    parts[0] = parts[0].replace(unkname, " any" + unkname)
                    parts[0] = " [ any" + unkname + " : " + self.simdata["unknowns"][unkname]["type"] + " ] " + parts[0]
                    # and include the original ones as theory
                    inc = self.include_in(subdict["theoryname"], unkname)
                for parname in string_handling.get_recursively(self.simdata["parameters"], "theoryname"):
                    inc = self.include_in(subdict["theoryname"], parname)

                # send declarations to mmt
                self.mmtinterface.mmt_new_decl("lhs", subdict["theoryname"], " mylhs = " + parts[0])
                reply_lhsconstant = self.mmtinterface.query_for(subdict["theoryname"])

                self.mmtinterface.mmt_new_decl("rhs", subdict["theoryname"], " myrhs = " + parts[1])
                reply_rhsconstant = self.mmtinterface.query_for(subdict["theoryname"])

                # create view
                self.new_view(subdict)
                ltype = self.get_inferred_type(subdict["theoryname"], "mylhs")
                eqtype = string_handling.get_last_type(ltype)
                rtype = self.get_inferred_type(subdict["theoryname"], "myrhs")
                self.mmtinterface.mmt_new_decl("eqtype", subdict["viewname"],
                                               "eqtype = " + eqtype)
                self.mmtinterface.mmt_new_decl("lhs", subdict["viewname"],
                                               "lhs = " + "mylhs")
                self.mmtinterface.mmt_new_decl("rhs", subdict["viewname"],
                                               "rhs = " + "myrhs")
                self.mmtinterface.mmt_new_decl("pde", subdict["viewname"],
                                               "pde = " + "[u](mylhs u) ≐ myrhs")

                reply = self.mmtinterface.query_for(subdict["theoryname"])

                for unkname in string_handling.get_recursively(self.simdata["unknowns"], "theoryname"):
                    op = subdict["lhsstring"].replace(unkname, "")
                    op = op.strip()

                # store the info
                subdict["op"] = op
                subdict["lhsparsestring"] = parts[0]
                subdict["rhsparsestring"] = parts[1]

                # TODO query number of effective pdes and unknowns from mmt for higher dimensional PDEs
                # => can assume each to be ==1 for now
                numpdesgiven = len(self.simdata["pdes"]["pdes"])
                self.poutput("Ok, " + reply.tostring())
                if numpdesgiven == len(self.simdata["unknowns"]):
                    self.trigger('pdes_parsed')
                elif numpdesgiven > len(self.simdata["unknowns"]):
                    self.poutput("now that's too many PDEs. Please go back and add more unknowns.")
                else:
                    self.poutput("More PDEs, please!")

    def pdes_exit(self):
        self.poutput("These are all the PDEs needed.")

    ##### for state bcs
    def bcs_begin(self):
        self.poutput("Let's discuss your boundary conditions. "
                     "What do they look like? u(x) = f(x) or u(" + str(self.simdata["domain"]["to"]) + ") = \\alpha ?")
        bctypetheoryname = self.redefine_bcs()
        with CriticalSubdict(self.simdata["bcs"], self.poutput) as subdict:
            subdict["theoryname"] = "ephbcs"
            subdict["bcs"] = []
            self.new_theory(subdict["theoryname"])
            # apparently, need to include everything explicitly so that view works
            for unknownentry in string_handling.get_recursively(self.simdata["unknowns"], "theoryname"):
                self.include_in(subdict["theoryname"], unknownentry)
            for paramentry in string_handling.get_recursively(self.simdata["parameters"], "theoryname"):
                self.include_in(subdict["theoryname"], paramentry)
            for pdeentry in string_handling.get_recursively(self.simdata["pdes"], "theoryname"):
                self.include_in(subdict["theoryname"], pdeentry)
            self.include_in(subdict["theoryname"], bctypetheoryname)
            self.new_view(subdict)
            subdict["measure_given"] = 0

    def bcs_handle_input(self, userstring):
        with CriticalSubdict(self.simdata["bcs"], self.poutput) as subdict:
            currentname = "bc" + str(len(subdict["bcs"]))
            subdict["bcs"].append({"name": currentname})
            # TODO use symbolic computation to order into LHS and RHS
            parts = re.split("=", userstring)

            if len(parts) is not 2:
                raise InterviewError("This does not look like a boundary condition.")
            # store the info
            subdict["bcs"][-1]["string"] = userstring
            subdict["bcs"][-1]["lhsstring"] = parts[0].strip()
            subdict["bcs"][-1]["rhsstring"] = parts[1].strip()  # TODO expand
            subdict["bcs"][-1]["rhsstring_expanded"] = self.try_expand(subdict["bcs"][-1]["rhsstring"])

            # to make a function on x, place " [ variablename : boundaryname ] " in front
            if "x" in parts[0]:
                parts[0] = " [ x : " + self.simdata["domain"]['boundary_name'] + " ] " + parts[0]
            if "x" in parts[1]:
                parts[1] = " [ x : " + self.simdata["domain"]['boundary_name'] + " ] " + parts[1]

            # in lhs replace all unknown names used by more generic ones and add lambda clause in front
            for unkname in string_handling.get_recursively(self.simdata["unknowns"], "theoryname"):
                parts[0] = parts[0].replace(unkname, " any" + unkname)
                parts[0] = " [ any" + unkname + " : " + self.simdata["unknowns"][unkname]["type"] + " ] " + parts[0]

                type = self.get_inferred_type(subdict["theoryname"], parts[0])
                if string_handling.type_is_function_to(type, self.simdata["unknowns"][unkname]["type"]):
                    # right-hand side: infer type, make function if not one yet
                    rhstype = self.get_inferred_type(subdict["theoryname"], parts[1])
                    if not string_handling.type_is_function_from(rhstype, self.simdata["domain"]["name"]) \
                            and not string_handling.type_is_function_from(rhstype, self.simdata["domain"]["boundary_name"]):
                        parts[1] = " [ x : " + self.simdata["domain"]["boundary_name"] + " ] " + parts[1]
                    self.add_list_of_declarations(subdict["viewname"], [
                        "firstBC = myDirichletBCfun " + parts[1],
                        "secondBC = myDirichletBCfun " + parts[1],
                    ])
                    subdict["bcs"][-1]["type"] = "Dirichlet",
                    subdict["bcs"][-1]["on"] = "x",
                    subdict["bcs"][-1]["measure"] = 2,
                    subdict["measure_given"] = 2
                elif string_handling.type_is_function_to(type, self.simdata["unknowns"][unkname]["codomain"]):
                    # at_x = re.split('[\(\)]', subdict["bcs"][-1]["lhsstring"])[-1] #TODO
                    at_x = subdict["bcs"][-1]["lhsstring"].split('(', 1)[1].split(')')[0].strip()
                    if at_x != self.simdata["domain"]["from"] and at_x != self.simdata["domain"]["to"]:
                        raise InterviewError(at_x + " is not on the boundary!")
                    if len(subdict["bcs"]) == 1:
                        self.mmtinterface.mmt_new_decl("bc1", subdict["viewname"],
                                                       "firstBC = solutionat " + at_x + " is " + parts[1])
                    elif len(subdict["bcs"]) == 2:
                        self.mmtinterface.mmt_new_decl("bc2", subdict["viewname"],
                                                       "secondBC = solutionat " + at_x + " is " + parts[1])
                    else:
                        raise InterviewError("too many boundary conditions saved")
                    subdict["measure_given"] += 1
                    subdict["bcs"][-1]["type"] = "Dirichlet",
                    subdict["bcs"][-1]["on"] = at_x,
                    subdict["bcs"][-1]["measure"] = 1,

            # try:
            #    type = self.get_inferred_type(subdict["theoryname"], "[u : Ω → ℝ] u(0.0)")
            #    type = self.get_inferred_type(subdict["theoryname"], "[u : Ω → ℝ] u")
            # except MMTServerError as error:
            #    self.poutput(error.args[0])

            self.poutput("Ok ")
            if subdict["measure_given"] == len(self.simdata["unknowns"]) * 2:  # TODO times inferred order of PDE
                self.trigger('bcs_parsed')
            elif subdict["measure_given"] > len(self.simdata["unknowns"]):
                raise InterviewError("now that's too many boundary conditions. ignoring last input.")
            else:
                self.poutput("Please enter more boundary conditions")

    def bcs_exit(self):
        self.poutput("These are all the boundary conditions needed.")
        self.print_empty_line()

    def redefine_bcs(self):
        for unknown in string_handling.get_recursively(self.simdata["unknowns"], "theoryname"):
            with CriticalSubdict(self.simdata["bcs"], self.poutput) as subdict:
                subdict["bctypes"] = {}
                bctypetheoryname = unknown + "BCTypes"
                subdict["bctypes"]["theoryname"] = bctypetheoryname
                self.new_theory(bctypetheoryname)
                self.include_in(bctypetheoryname, unknown)
                self.include_in(bctypetheoryname, "mDifferentialOperators")
                self.add_list_of_declarations(bctypetheoryname,
                                              [
                                                  "myDirichletBC: {where: " + self.simdata["domain"][
                                                      "boundary_name"] + ", rhs: " +
                                                  self.simdata["unknowns"][unknown]["codomain"] + "}(" +
                                                  self.simdata["domain"]["name"] + " → " +
                                                  self.simdata["unknowns"][unknown]["codomain"] + ") → prop "
                                                                                                  " ❘ = [where, rhs][u] u where ≐ rhs ❘  # solutionat 1 is 2 ",
                                                  "myDirichletBCfun : {rhs: " + self.simdata["domain"][
                                                      "boundary_name"] + " → " +
                                                  self.simdata["unknowns"][unknown]["codomain"] + " }(" +
                                                  self.simdata["domain"]["name"] + " → " +
                                                  self.simdata["unknowns"][unknown][
                                                      "codomain"] + ") → prop ❘ = [rhs] [u] ∀[x:" +
                                                  self.simdata["domain"]["boundary_name"] + " ] u x ≐ rhs x "
                                                                                            "❘ # solutionatboundaryis 1",
                                              ]
                                              )
                viewname = bctypetheoryname + "ASmBCTypes"
                subdict["bctypes"]["viewname"] = viewname
                self.mmtinterface.mmt_new_view(viewname, "mBCTypes", bctypetheoryname)
                self.include_former_views(viewname)
                self.add_list_of_declarations(viewname,
                                              ["DirichletBC = myDirichletBC ",
                                               # " = myDirichletBCfun"
                                               ])
                return bctypetheoryname  # Todo adapt for more than 1

    ##### for state props
    def props_begin(self):
        with CriticalSubdict(self.simdata["props"], self.poutput) as subdict:
            # TODO try to find out things about the solvability ourselves
            subdict["theoryname"] = "ephBoundaryValueProblem"
            self.new_theory(subdict["theoryname"])
            # apparently, need to include everything explicitly so that view works
            for unknownentry in string_handling.get_recursively(self.simdata["unknowns"], "theoryname"):
                self.include_in(subdict["theoryname"], unknownentry)
            for paramentry in string_handling.get_recursively(self.simdata["parameters"], "theoryname"):
                self.include_in(subdict["theoryname"], paramentry)
            for pdeentry in string_handling.get_recursively(self.simdata["pdes"], "theoryname"):
                self.include_in(subdict["theoryname"], pdeentry)
            self.include_in(subdict["theoryname"], self.simdata["bcs"]["theoryname"])
            self.new_view(subdict)
            self.include_trivial_assignment(subdict["viewname"], "mDifferentialOperators")
            self.include_trivial_assignment(subdict["viewname"], "mLinearity")

            subdict["ops"] = []
            for pde in self.simdata["pdes"]["pdes"]:
                self.poutput("Do you know something about the operator " + pde["op"] + "? "
                                                                                       "Is it e.g. linear, or not elliptic ? ")
                subdict["ops"].append({})
                subdict["ops"][-1]["name"] = pde["op"]
                subdict["ops"][-1]["props"] = []

    def props_handle_input(self, userstring):
        if string_handling.means_no(userstring):
            self.trigger("props_parsed")
            return

        with CriticalSubdict(self.simdata["props"], self.poutput) as subdict:
            #            "linear": True, #or false or unknown
            #            "props": ["elliptic"]

            parsestring = userstring.replace("not", "¬")

            if "linear" in parsestring:
                self.add_list_of_declarations(subdict["theoryname"], [
                    string_handling.add_ods("user_linear : ⊦ " + parsestring + ' mylhs = sketch "user knowledge" ')
                ])
                if "¬" in parsestring:
                    subdict["ops"][-1]["linear"] = False
                else:
                    subdict["ops"][-1]["linear"] = True
                    self.add_list_of_declarations(subdict["viewname"], [
                        "isLinear = user_linear"
                    ])
                self.poutput("OK!")

            for property in ["elliptic"]:  # TODO more properties
                if property in parsestring:
                    self.add_list_of_declarations(subdict["theoryname"], [
                        string_handling.add_ods("user_" + property + " : ⊦ " + parsestring + ' mylhs = sketch "user knowledge" ')
                    ])
                    subdict["ops"][-1]["props"].append(parsestring)
                    if "¬" not in parsestring:
                        self.add_list_of_declarations(subdict["viewname"], [
                            "isElliptic = user_elliptic"
                        ])
                    self.poutput("OK!")
            self.poutput("do you know anything else?")

    def props_exit(self):
        # TODO totality check on the view from uniquelysolvable to ephBoundaryValueProblem
        return

    ##### for state sim
    def sim_begin(self):
        self.please_prompt("Would you like to try and solve the PDE using the Finite Difference Method in ExaStencils? "
                           "If yes, you can provide a configuration name, or we'll just use your name.",
                           if_yes=self.sim_ok_fd, if_no=None, pass_other=True)

    def sim_handle_input(self, userstring):
        self.sim_exit(userstring)

    def sim_ok_fd(self):
        self.sim_exit()

    def sim_exit(self, problem_name=None):
        self.simdata["sim"]["type"] = "FiniteDifferences"
        # generate output
        self.exaout = ExaOutput(self.simdata, getpass.getuser(), problem_name)
        print("Generated ExaStencils input; running ExaStencils")
        # generate and run simulation
        runner = ExaRunner(self.exaout)
        runner.run_exastencils()
        print("Ran ExaStencils; preparing visualization")
        # output
        self.display_result_as_bokeh()

    # cf. nbviewer.jupyter.org/github/bokeh/bokeh-notebooks/blob/master/tutorial/01 - Basic Plotting.ipynb
    def display_result_as_bokeh(self):

        unknowns = [*self.simdata["unknowns"]]

        # create a new plot with default tools, using figure
        p = figure(plot_width=1000, plot_height=400)

        runner = ExaRunner(self.exaout)
        data = runner.load_data(unknowns[0])  # TODO more dimensions
        source = ColumnDataSource(data=data)
        source.data = source.from_df(data)
        source.add(data.index, 'index')

        # add a circle renderer with a size, color, and alpha
        p.circle(x='index', y=unknowns[0], size=2, line_color="navy", fill_color="orange", fill_alpha=0.5, source=source)
        #show(p)

        output_notebook()
        # cf. http://bokeh.pydata.org/en/0.10.0/docs/user_guide/embed.html
        self.display_html(file_html(p, CDN, "my plot"))  # show the results

        # using JS requires jupyter widgets extension
        # script, div = components(p)
        # div = notebook_div(p)
        # self.Display(Javascript(script + div))  # show the results

    def generate_mpd_theories(self):
        with CriticalSubdict({}, self.poutput):
            # generate Laws that define the parameters, if applicable
            for paramentry in string_handling.get_recursively(self.simdata["parameters"], "theoryname"):
                mpd_theory_name = "MPD_" + paramentry
                self.mmtinterface.mmt_new_theory(mpd_theory_name)
                self.include_in(mpd_theory_name, paramentry)
                if self.mmtinterface.query_for(paramentry).hasDefinition(paramentry):
                    self.add_list_of_declarations(mpd_theory_name, [
                        "proof_" + paramentry + " : ⊦ " + self.simdata["parameters"][paramentry]["parsestring"].replace("=", "≐")
                        + string_handling.object_delimiter + " role Law"
                    ])

            # generate the Quantity of a hypothetical solution to an unknown
            for unknownentry in string_handling.get_recursively(self.simdata["unknowns"], "theoryname"):
                mpd_theory_name = "MPD_" + unknownentry
                self.mmtinterface.mmt_new_theory(mpd_theory_name)
                self.include_in(mpd_theory_name, unknownentry)
                self.add_list_of_declarations(mpd_theory_name, [
                    unknownentry + " : " + self.simdata["unknowns"][unknownentry]["type"]
                    + string_handling.object_delimiter + " role Quantity"
                ])

            # generate the Laws that define it, namely boundary conditions and PDEs #TODO BCs
            for pdeentry in string_handling.get_recursively(self.simdata["pdes"], "theoryname"):
                mpd_theory_name = "MPD_" + pdeentry
                self.mmtinterface.mmt_new_theory(mpd_theory_name)
                self.include_in(mpd_theory_name, pdeentry)

                #include all the mpd_unknowns, parameters and bcs #TODO
                for unknownentry in string_handling.get_recursively(self.simdata["unknowns"], "theoryname"):
                    self.include_in(mpd_theory_name, "MPD_" + unknownentry)

                for paramentry in string_handling.get_recursively(self.simdata["parameters"], "theoryname"):
                    self.include_in(mpd_theory_name, paramentry)

                self.add_list_of_declarations(mpd_theory_name, [
                    "proof_" + pdeentry + " : ⊦ " + self.simdata["pdes"]["pdes"][pdeentry]["lhsstring"] +
                    " ≐ " + self.simdata["pdes"]["pdes"][pdeentry]["rhsstring"]
                    + string_handling.object_delimiter + " role Law"
                ])

            # make an actual model theory that includes all of the Laws declared so far,
            # which in turn include the Quantities
            modelname = "Model"
            self.mmtinterface.mmt_new_theory(modelname)
            # include all the mpd_parameters, mpd_pdes and mpd_bcs #TODO
            for paramentry in string_handling.get_recursively(self.simdata["parameters"], "theoryname"):
                self.include_in(modelname, "MPD_" + paramentry)
            for pdeentry in string_handling.get_recursively(self.simdata["pdes"], "theoryname"):
                self.include_in(modelname, "MPD_" + pdeentry)

            return modelname

    # functions for user interaction
    def obviously_stupid_input(self):
        self.poutput("Trying to be funny, huh?")

    # mmt input helper functions
    def include_in(self, in_which_theory, what):
        return self.mmtinterface.mmt_new_decl("inc", in_which_theory, "include " + string_handling.assert_question_mark(what))

    def add_list_of_declarations(self, in_which_theory, declaration_list):
        for declaration in declaration_list:
            self.mmtinterface.mmt_new_decl("inc", in_which_theory, declaration)

    def include_bgthys(self, in_which_theory):
        """Includes all the background theories specified in self.bgthys for the current state"""
        ok = True
        for bgthy in self.bgthys[self.state]:
            ok = ok and self.include_in(in_which_theory, bgthy)
        return ok

    def new_theory(self, thyname):
        self.mmtinterface.mmt_new_theory(thyname)
        return self.include_bgthys(thyname)

    def new_view(self, dictentry):
        """Constructs a new entry 'viewname' into the given dictionary and creates the view,
        including all applicable former views"""
        dictentry["viewname"] = self.construct_current_view_name(dictentry)
        # self.poutput("new view: "+dictentry["viewname"])
        self.mmtinterface.mmt_new_view(dictentry["viewname"], self.viewfrom[self.state], dictentry["theoryname"])
        return self.include_former_views(dictentry["viewname"])

    def include_former_views(self, current_view_name):
        """recursively look for all views already done and try to include them into the current view."""
        for viewstring in string_handling.get_recursively(self.simdata, "viewname"):
            if (current_view_name != viewstring):
                try:
                    self.include_in(current_view_name,
                                    "?" + string_handling.split_string_at_AS(viewstring)[-1] + " = " + "?" + viewstring)
                except MMTServerError as error:
                    # self.poutput("no backend available that is applicable to " + "http://mathhub.info/MitM/smglom/calculus" + "?" + re.split('AS', dictentry["viewname"])[-1] + "?")
                    # we are expecting errors if we try to include something that is not referenced in the source theory, so ignore them
                    expected_str = "no backend available that is applicable to " + self.mmtinterface.namespace + "?" + re.split('AS', current_view_name)[-1] + "?"
                    if expected_str not in error.args[0]:
                        raise

    def construct_current_view_name(self, dictentry):
        return self.construct_view_name(dictentry, self.state)

    def construct_view_name(self, dictentry, state):
        return dictentry["theoryname"] + "AS" + (self.viewfrom[state])

    def include_trivial_assignment(self, in_view, theoryname):
        self.include_in(in_view, string_handling.assert_question_mark(theoryname) + " = " + string_handling.assert_question_mark(theoryname))

    def get_inferred_type(self, in_theory, term):
        return self.mmtinterface.mmt_infer_type(in_theory, term).inferred_type_to_string()

    def try_expand(self, term,
                   in_theory=None):  # TODO do using mmt definition expansion, issue UniFormal/MMT/issues/295
        for param in reversed(self.simdata["parameters"]):
            if param in term:
                parts = self.simdata["parameters"][param]["string"].split("=")
                if (len(parts) != 2):
                    raise InterviewError("no definition for " + param + " given")
                paramdef = parts[-1]
                term = term.replace(param, paramdef.strip())
        return term

    def print_empty_line(self):
        self.poutput("\n")

    def explain(self, userstring=None):  # TODO
        with CriticalSubdict({}, self.poutput):
            reply = self.mmtinterface.query_for(
                "http://mathhub.info/smglom/calculus/nderivative.omdoc?nderivative?nderivative")
            self.poutput(reply.tostring())

    def recap(self, userstring=None):  # TODO
        self.print_simdata()

    def print_simdata(self):
        for s in reversed(self.states):
            state_name = s.name
            if state_name in self.simdata:
                self.poutput(state_name + ": " + str(self.simdata[state_name]))
            if state_name == self.state:
                return

