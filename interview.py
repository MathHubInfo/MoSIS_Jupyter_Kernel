#!/usr/bin/env python3

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
import re

from exaoutput import ExaOutput
from mmtinterface import *


class InterviewError(Exception):
    def __init__(self, err):
        self.error = err
        super(InterviewError, self).__init__("Interview error: " + str(self.error))


def means_no(answer):
    try:
        ret = strtobool(answer)
        if ret == False:
            return True
    except ValueError:
        return False
    return False


###For the part of the simdata whose contents will be cleaned up if there was an error
###to be used in with statements
class CriticalSubdict():
    def __init__(self, subdict):
        self.subdict = subdict
        self.initial_subdict = self.subdict.copy()

    def __enter__(self):
        return self.subdict

    def __exit__(self, type, value, traceback):
        if type is not None:
            #restore the initial state
            self.subdict.clear()
            for key in self.initial_subdict:
                self.subdict[key] = self.initial_subdict[key]
            print(value)
            if isinstance(value, MMTServerError) or isinstance(value, InterviewError):
                self.please_repeat(value)
                return False
            else:
                return False
        return True

    def please_repeat(self, moreinfo=None):
        append = ""
        if moreinfo:
            append = "\nDetails: " + moreinfo
        print("I did not catch that. Could you please rephrase?" + append)


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
            State('bcs', on_enter=['bcs_begin'], on_exit=['bcs_exit']),
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
        self.machine.add_transition(trigger='sim_finished', source='sim', dest='sim', before='print_empty_line')

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
            'pdes': self.pdes_handle_input,
            'bcs': self.bcs_handle_input,
            'sim': self.sim_handle_input,
        }

        self.mmtinterface = MMTInterface()

        # for ladder-like views
        self.viewfrom = OrderedDict([
            ('domain', "mDomain"),
            ('unknowns', "mUnknown"),
            ('parameters', "mParameter"),
            ('pdes', "mPDE"),
            ('bcs', "mBCsRequired"),
            ('sim', "mEllipticLinearDirichletBoundaryValueProblem"),
        ])
        # to include all the necessary theories every time
        self.bgthys = OrderedDict([
            ('domain', ["mInterval", "http://mathhub.info/MitM/smglom/arithmetics?realarith"]),
            # new: RealArithmetics
            ('unknowns', ["http://mathhub.info/MitM/Foundation?Strings", "ephdomain",
                          "http://mathhub.info/MitM/smglom/calculus?higherderivative"]),
            ('parameters', ["http://mathhub.info/MitM/smglom/arithmetics?realarith", "ephdomain"]),
            ('pdes', ["mDifferentialOperators"]),#+params, unknowns,
            ('bcs',
             ["ephdomain", "mLinearity",
              "http://mathhub.info/MitM/smglom/arithmetics?realarith"]),#+params, unknowns, pdes, bctypes
            ('sim',
             ["mLinearity",
              "http://mathhub.info/MitM/Foundation?Strings"]), #+bcs, pde
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
            "bcs": {
                "theoryname": None,
                "bcs": None,
            },
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
            "bcs": {
                "theoryname": "ephbcs",
                "bcs": [
                    {
                        "name": "bc1",
                        "type": "Dirichlet",
                        "string": "u (0) = x_1**2",
                        "on": "[0]",
                    },
                    {
                        "name": "bc2",
                        "type": "Dirichlet",
                        "string": "u (1) = x_1**2",
                        "on": "[1]",
                    },
                ],
            },
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
            self.dimensions_begin()
        elif numdim == 1:  # or self.numdim == 2:
            self.simdata["num_dimensions"] = numdim
            self.dimensions_parsed()
        else:
            self.poutput(
                "Sorry, cannot handle " + str(self.numdim) + " dimensions as of now. Please try less than that.")

    ##### for state domain
    def domain_begin(self):
        self.poutput("What is the domain you would like to simulate for?     Ω : type ❘ = [?;?], e.g. Ω = [0.0;1.0]")
        self.poutput("By the way, you can always try and use LaTeX-type input.")
        self.simdata[self.state]["axes"] = OrderedDict()
        self.domain_mmt_preamble()

    def domain_handle_input(self, userstring):
        domain_name = get_first_word(userstring)
        # subdict = self.simdata[self.state]
        with CriticalSubdict(self.simdata[self.state]) as subdict:
            parsestring = userstring
            mmtreply = self.mmtinterface.mmt_new_decl(domain_name, subdict["theoryname"], parsestring)
            mmtreply = self.mmtinterface.mmt_infer_type(subdict["theoryname"], domain_name)
            if mmtreply.inferred_type_to_string() != "type":
                raise InterviewError("This seems to not be a type. It should be!")
            result = self.mmtinterface.query_for(subdict["theoryname"])  # if not self.cheating else
            # print(mmtreply.tostring())
            subdict["name"] = domain_name
            (fro, to) = mmtreply.getIntervalBoundaries(mmtreply, domain_name) if not self.cheating else ("0.", "1.")  # todo make work again
            subdict["axes"]["x_1"] = "[" + fro + ";" + to + "]"
            (subdict["from"], subdict["to"]) = ("[ " + fro + " ]", "[ " + to + " ]")

            self.poutput("we will just assume that the variable is called x for now.")
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
        with CriticalSubdict(self.simdata[self.state]) as subdict:
            subdict["boundary_name"] = subdict["name"] #todo
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
        unknown_name = get_first_word(userstring)
        # replace interval with domain
        parsestring = (
            userstring.replace(self.simdata["domain"]["name"],
                               "pred myDomainPred") if not self.cheating else userstring)

        with CriticalSubdict(self.simdata[self.state]) as usubdict:
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
            with CriticalSubdict(self.simdata["unknowns"][unknown_name]) as subdict:
                if self.mmtinterface.query_for(unknown_name + "_to_go_to_trash").hasDefinition(unknown_name):
                    raise InterviewError("Unknowns cannot be defined!")
                if not type_is_function_from(subdict["type"], self.simdata["domain"]["name"]):
                    raise InterviewError("Unknown should be a function on " + self.simdata["domain"]["name"] + "!")

                # add unknown's type as constant
                twice = self.mmtinterface.mmt_new_decl(unknown_name, subdict["theoryname"],
                                                       "myUnkType = " + subdict["type"])
                twice = (self.mmtinterface.mmt_new_decl('diffable', subdict["theoryname"],
                                                        "anyuwillbediffable : {u : myUnkType} ⊦ twodiff u ") if not self.cheating else twice)
                self.new_view(subdict)
                self.mmtinterface.mmt_new_decl("codomain", subdict["viewname"],
                                                                             "ucodomain = " + subdict["codomain"]) # TODO
                self.mmtinterface.mmt_new_decl("unktype", subdict["viewname"],
                                                                              "unknowntype = myUnkType")
                self.poutput("Ok, " + userstring)
                if self.please_prompt("Are these all the unknowns?"):
                    self.trigger('unknowns_parsed')

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
        if means_no(userstring):
            self.trigger('parameters_parsed')
            return

        parameter_name = get_first_word(userstring)
        self.simdata["parameters"][parameter_name] = {}
        with CriticalSubdict(self.simdata["parameters"][parameter_name]) as subdict:
            # create mmt theory
            self.new_theory(parameter_name)
            # we might need the other parameters created so far, so use them
            for otherparamentry in get_recursively(self.simdata["parameters"], "theoryname"):
                self.include_in(parameter_name, otherparamentry)

            # sanitize userstring - check if this works for all cases
            parsestring = add_ods(userstring)
            parsestring = functionize(parsestring, self.simdata["domain"]["name"])
            # self.poutput(parsestring)
            reply_pconstant = self.mmtinterface.mmt_new_decl("param", parameter_name, parsestring)
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
            if self.please_prompt("Are these all the parameters?"):
                self.trigger('parameters_parsed')

    def parameters_exit(self):
        # print(str(self.simdata["parameters"]))
        for parameter in self.simdata["parameters"]:
            self.poutput(self.simdata["parameters"][parameter]["string"])

    ##### for state pdes
    def pdes_begin(self):
        self.poutput(
            "Let's get to your partial differential equation(s). What do they look like? Δu = 0.0, or laplace_operator Ω ℝ u = f ?")
        self.simdata["pdes"]["pdes"] = []

    def pdes_handle_input(self, userstring):
        self.simdata["pdes"]["pdes"].append({})
        with CriticalSubdict(self.simdata["pdes"]["pdes"][-1]) as subdict:
            subdict["theoryname"] = "ephpde" + str(len(self.simdata["pdes"]["pdes"]))
            self.new_theory(subdict["theoryname"])

            # TODO use symbolic computation to order into LHS and RHS
            parts = re.split("=", userstring)

            if len(parts) is not 2:
                raise InterviewError("This does not look like an equation.")

            # store the info
            subdict["string"] = userstring
            subdict["lhsstring"] = parts[0]
            subdict["rhsstring"] = parts[1]

            # to make the left-hand side a function on x, place " [ variablename : domainname ] " in front
            if parts[0].find("x") > -1:
                parts[0] = " [ x : " + self.simdata["domain"]["name"] + " ] " + parts[0]
            # right-hand side: infer type, make function if not one yet
            if not type_is_function_from(self.get_inferred_type(subdict["theoryname"], parts[1]),
                                         self.simdata["domain"]["name"]):
                parts[1] = " [ x : " + self.simdata["domain"]["name"] + " ] " + parts[1]

            # in lhs replace all unknown names used by more generic ones and add lambda clause in front
            for unkname in get_recursively(self.simdata["unknowns"], "theoryname"):
                parts[0] = parts[0].replace(unkname, " any" + unkname)
                parts[0] = " [ any" + unkname + " : " + self.simdata["unknowns"][unkname]["type"] + " ] " + parts[0]
                # and include the original ones as theory
                inc = self.include_in(subdict["theoryname"], unkname)
            for parname in get_recursively(self.simdata["parameters"], "theoryname"):
                inc = self.include_in(subdict["theoryname"], parname)

            # send declarations to mmt
            reply_lhsconstant = self.mmtinterface.mmt_new_decl("lhs", subdict["theoryname"], " mylhs = " + parts[0])
            if reply_lhsconstant.ok:
                reply_lhsconstant = self.mmtinterface.query_for(subdict["theoryname"])

            reply_rhsconstant = self.mmtinterface.mmt_new_decl("rhs", subdict["theoryname"], " myrhs = " + parts[1])
            if reply_rhsconstant.ok:
                reply_rhsconstant = self.mmtinterface.query_for(subdict["theoryname"])

            # create view
            self.new_view(subdict)
            ltype = self.get_inferred_type(subdict["theoryname"], "mylhs")
            eqtype = get_last_type(ltype)
            rtype = self.get_inferred_type(subdict["theoryname"], "myrhs")
            self.mmtinterface.mmt_new_decl("eqtype", subdict["viewname"],
                                                                     "eqtype = " + eqtype)
            self.mmtinterface.mmt_new_decl("lhs", subdict["viewname"],
                                                                     "lhs = " + "mylhs")
            self.mmtinterface.mmt_new_decl("rhs", subdict["viewname"],
                                                                     "rhs = " + "myrhs")
            self.mmtinterface.mmt_new_decl("pde", subdict["viewname"],
                                                                     "pde = " + "[u](mylhs u) funcEq myrhs")

            reply = self.mmtinterface.query_for(subdict["theoryname"])

            for unkname in get_recursively(self.simdata["unknowns"], "theoryname"):
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
        self.poutput(
            "Let's get to your boundary conditions. What do they look like? solutionat 0.0 is 1.0 or solutionatboundaryis f ?")
        bctypetheoryname = self.redefine_bcs()
        with CriticalSubdict(self.simdata["bcs"]) as subdict:
            subdict["theoryname"] = "ephbcs"
            subdict["bcs"] = []
            self.new_theory(subdict["theoryname"])
            # apparently, need to include everything explicitly so that view works
            for unknownentry in get_recursively(self.simdata["unknowns"], "theoryname"):
                self.include_in(subdict["theoryname"], unknownentry)
            for paramentry in get_recursively(self.simdata["parameters"], "theoryname"):
                self.include_in(subdict["theoryname"], paramentry)
            for pdeentry in get_recursively(self.simdata["pdes"], "theoryname"):
                self.include_in(subdict["theoryname"], pdeentry)
            self.include_in(subdict["theoryname"], bctypetheoryname)
            self.new_view(subdict)
            subdict["measure_given"] = 0

    def bcs_handle_input(self, userstring):
        with CriticalSubdict(self.simdata["bcs"]) as subdict:
            currentname = "bc" + str(len(subdict["bcs"]))
            subdict["bcs"].append({"name": currentname})
            # TODO use symbolic computation to order into LHS and RHS
            parts = re.split("=", userstring)

            if len(parts) is not 2:
                raise InterviewError("This does not look like a boundary condition.")
            # store the info
            subdict["bcs"][-1]["string"] = userstring
            subdict["bcs"][-1]["lhsstring"] = parts[0]
            subdict["bcs"][-1]["rhsstring"] = parts[1]

            # to make a function on x, place " [ variablename : boundaryname ] " in front
            if parts[0].find("x") > -1:
                parts[0] = " [ x : " + self.simdata["domain"]['boundary_name'] + " ] " + parts[0]
            if parts[1].find("x") > -1:
                parts[1] = " [ x : " + self.simdata["domain"]['boundary_name'] + " ] " + parts[1]

            # in lhs replace all unknown names used by more generic ones and add lambda clause in front
            for unkname in get_recursively(self.simdata["unknowns"], "theoryname"):
                parts[0] = parts[0].replace(unkname, " any" + unkname)
                parts[0] = " [ any" + unkname + " : " + self.simdata["unknowns"][unkname]["type"] + " ] " + parts[0]

                type = self.get_inferred_type(subdict["theoryname"], parts[0])
                if type_is_function_to(type, self.simdata["unknowns"][unkname]["type"]):
                    # right-hand side: infer type, make function if not one yet
                    rhstype = self.get_inferred_type(subdict["theoryname"], parts[1])
                    if not type_is_function_from(rhstype, self.simdata["domain"]["name"])\
                            and not type_is_function_from(rhstype, self.simdata["domain"]["boundary_name"]):
                        parts[1] = " [ x : " + self.simdata["domain"]["name"] + " ] " + parts[1]
                    self.add_list_of_declarations(subdict["viewname"], [
                        "firstBC = myDirichletBCfun " + parts[1],
                        "secondBC = myDirichletBCfun " + parts[1],
                    ])
                    subdict["measure_given"] = 2
                elif type_is_function_to(type, self.simdata["unknowns"][unkname]["codomain"]):
                    at_x = re.split('\(\)', subdict["bcs"][-1]["lhsstring"])[-1] #TODO
                    if len(subdict["bcs"]) == 1:
                        self.mmtinterface.mmt_new_decl("bc1", subdict["viewname"],
                                                       "firstBC = solutionat " + at_x + "is" + parts[1] )
                    elif len(subdict["bcs"]) == 2:
                        self.mmtinterface.mmt_new_decl("bc2", subdict["viewname"],
                                                       "secondBC = " + subdict["bcs"][-1]["name"])#TODO
                    else:
                        raise InterviewError("too many boundary conditions saved")
                    subdict["measure_given"] += 1

            #try:
            #    type = self.get_inferred_type(subdict["theoryname"], "[u : Ω → ℝ] u(0.0)")
            #    type = self.get_inferred_type(subdict["theoryname"], "[u : Ω → ℝ] u")
            #except MMTServerError as error:
            #    self.poutput(error.args[0])

            self.poutput("Ok ")
            if subdict["measure_given"] == len(self.simdata["unknowns"])*2: #TODO times order
                self.trigger('bcs_parsed')
            elif subdict["measure_given"] > len(self.simdata["unknowns"]):
                raise InterviewError("now that's too many boundary conditions. ignoring last input.")

    def bcs_exit(self):
        self.poutput("These are all the boundary conditions needed.")

    def redefine_bcs(self):
        for unknown in get_recursively(self.simdata["unknowns"], "theoryname"):
            with CriticalSubdict(self.simdata["bcs"]) as subdict:
                subdict["bctypes"] = {}
                bctypetheoryname = unknown + "BCTypes"
                subdict["bctypes"]["theoryname"] = bctypetheoryname
                self.new_theory(bctypetheoryname)
                self.include_in(bctypetheoryname, unknown)
                self.include_in(bctypetheoryname, "mDifferentialOperators")
                self.add_list_of_declarations(bctypetheoryname,
                        [
                            "myDirichletBC: {where: " + self.simdata["domain"]["boundary_name"] + ", rhs: " +
                                self.simdata["unknowns"][unknown]["codomain"] + "}(" + self.simdata["domain"]["name"] + " → " +
                                self.simdata["unknowns"][unknown]["codomain"] + ") → prop "
                                " ❘ = [where, rhs][u] u where ≐ rhs ❘  # solutionat 1 is 2 ",
                            "myDirichletBCfun : {rhs: " + self.simdata["domain"]["boundary_name"] + " → " +
                                self.simdata["unknowns"][unknown]["codomain"] + " }(" + self.simdata["domain"]["name"] + " → " +
                                self.simdata["unknowns"][unknown]["codomain"] + ") → prop ❘ = [rhs] [u] ∀[x:" + self.simdata["domain"]["boundary_name"] + " ] u x ≐ rhs x "
                                "❘ # solutionatboundaryis 1",
                        ]
                )
                #viewname = bctypetheoryname + "ASmBCTypes"
                #subdict["bctypes"]["viewname"] = viewname
                #self.mmtinterface.mmt_new_view(viewname, bctypetheoryname, "mBCTypes")
                #self.add_list_of_declarations(viewname,
                #                              ["DirichletBC = myDirichletBC ",
                #                               #" = myDirichletBCfun"
                #                               ])
                return bctypetheoryname  # Todo adapt for more than 1

    ##### for state sim
    def sim_begin(self):
        # TODO try to find out things about the solvability ourselves
        self.simdata[self.state]["theoryname"] = "ephEllipticLinearDirichletBoundaryValueProblem"
        self.new_theory(self.simdata[self.state]["theoryname"])
        self.new_view(self.simdata[self.state]["theoryname"])
        for pde in self.simdata["pdes"]["pdes"]:
            self.poutput("Do you know something about the operator " + pde["op"] + "?"
                         "Is it e.g. linear, elliptic, not hyperbolic ? ")

    def sim_handle_input(self, userstring):
        if means_no(userstring):
            self.poutput("Ok, let's try to simulate it.")
            self.sim_exit()
            return

        # TODO offer a solution algorithm and implementation if all necessary things are defined
        with CriticalSubdict(self.simdata["sim"]) as subdict:
            #parts = re.split(" ", userstring)
            parsestring = userstring.replace("not", "¬")
            for property in ["linear", "elliptic"]:
                if parsestring.find(property) > -1:
                    self.add_list_of_declarations(subdict["theoryname"], [
                        "user_" + property + " : ⊦ " + parsestring + "mylhs"
                    ])
            self.poutput("OK!")
            self.poutput("do you know anything else?")

    def sim_exit(self):
        # generate output
        self.exaout.create_output(self.simdata)
        self.poutput("Generated ExaStencils input.")
        #TODO generate and run simulation

    #### functions for user interaction
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

    def obviously_stupid_input(self):
        self.poutput("Trying to be funny, huh?")

    # mmt input helper functions
    def include_in(self, in_which_theory, what):
        return self.mmtinterface.mmt_new_decl("inc", in_which_theory, "include " + assert_questionmark(what))

    def add_list_of_declarations(self, in_which_theory, declaration_list):
        for declaration in declaration_list:
            self.mmtinterface.mmt_new_decl("inc", in_which_theory, declaration)

    def include_bgthys(self, in_which_theory):
        ok = True
        for bgthy in self.bgthys[self.state]:
            ok = ok and self.include_in(in_which_theory, bgthy)
        return ok

    def new_theory(self, thyname):
        try:
            self.mmtinterface.mmt_new_theory(thyname)
            return self.include_bgthys(thyname)
        except MMTServerError as error:
            self.poutput(error.args[0])
            # self.poutput(error.with_traceback())
            raise
        # (ok, root) = self.mmtinterface.query_for(self.simdata[self.state]["theoryname"])

    def new_view(self, dictentry):
        dictentry["viewname"] = self.construct_current_view_name(dictentry)
        # self.poutput("new view: "+dictentry["viewname"])
        ok = self.mmtinterface.mmt_new_view(dictentry["viewname"], self.viewfrom[self.state], dictentry["theoryname"])
        # recursively look for all views already done and try to include them
        for viewstring in get_recursively(self.simdata, "viewname"):
            if (dictentry["viewname"] != viewstring) and ok:
                try:
                    ok = self.include_in(dictentry["viewname"],
                                         "?" + re.split('AS', viewstring)[-1] + " = " + "?" + viewstring)
                except MMTServerError as error:
                    # self.poutput("no backend available that is applicable to " + "http://mathhub.info/MitM/smglom/calculus" + "?" + re.split('AS', dictentry["viewname"])[-1] + "?")
                    # we are expecting errors if we try to include something that is not referenced in the source theory, so ignore them
                    if error.args[0].find(
                            "no backend available that is applicable to " + "http://mathhub.info/MitM/smglom/calculus" + "?" +
                            re.split('AS', dictentry["viewname"])[-1] + "?") < 1:
                        raise
        return ok

    def construct_current_view_name(self, dictentry):
        return self.construct_view_name(dictentry, self.state)

    def construct_view_name(self, dictentry, state):
        return dictentry["theoryname"] + "AS" + (self.viewfrom[state])

    def get_inferred_type(self, in_theory, term):
        return self.mmtinterface.mmt_infer_type(in_theory, term).inferred_type_to_string()

    def print_empty_line(self):
        self.poutput("\n")

    ############# input processing if not explain or undo
    def default(self, line):
        raw = line.parsed['raw']
        arg = LatexNodes2Text().latex_to_text(raw)
        # pythonic switch-case, cf. https://bytebaker.com/2008/11/03/switch-case-statement-in-python/
        try:
            self.stateDependentInputHandling[self.state](arg)
        except Exception as error:
            self.exaout.create_output(self.simdata)
            raise

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
                'parameters': ['f :  ℝ → ℝ = [x: ℝ] x '],  # ['f : Ω → ℝ = [x:Ω] x ⋅ x'],
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


# cf. https://stackoverflow.com/questions/14962485/finding-a-key-recursively-in-a-dictionary
def get_recursively(search_dict, field):
    """
    Takes a dict with nested lists and dicts, and searches all dicts for a key of the field provided,
    returning a list of the values.
    """
    fields_found = []
    for key, value in search_dict.items():
        if key == field:
            fields_found.append(value)
        elif isinstance(value, dict):
            results = get_recursively(value, field)
            for result in results:
                fields_found.append(result)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    more_results = get_recursively(item, field)
                    for another_result in more_results:
                        fields_found.append(another_result)
    return fields_found


# """string modification functions"""
def insert_type(string, whichtype):
    eqidx = string.find("=")
    if eqidx < 0:
        raise Exception
    if not self.has_colon(string):
        # print('has no colon ' + equidx)
        return string[:eqidx] + " : " + whichtype + " ❘ " + string[eqidx:]
    return string[:eqidx] + " ❘ " + string[eqidx:]


def type_is_function_from(type_string, from_string):
    if type_string.startswith(from_string + " →"):
        return True
    if type_string.startswith("{ : " + from_string):
        return True

    from_string = make_list_of_type_symbols(from_string)
    type_string = make_list_of_type_symbols(type_string)

    if len(from_string) > len(type_string):
        return False

    for index in range(len(from_string)):
        if from_string[index] != type_string[index]:
            return False

    return True

def type_is_function_to(type_string, to_string):
    if type_string.endswith("→ " + to_string):
        return True
    if type_string.endswith("} " + to_string):
        return True
    to_string = make_reverse_list_of_type_symbols(to_string)
    type_string = make_reverse_list_of_type_symbols(type_string)

    if len(to_string) > len(type_string):
        return False

    for index in range(len(to_string)):
        if to_string[index] != type_string[index]:
            return False

    return True

def insert_before_def(string, insertstring):
    eqidx = string.find("=")
    if eqidx < 0:
        raise Exception
    return string[:eqidx + 1] + " " + insertstring + " " + string[eqidx + 1:]


def get_first_word(string):
    return re.split('\W+', string, 1)[0]


def get_last_type(string):
    string = remove_round_brackets(string)
    string = string.rstrip()
    return re.split('[→ \s]', string)[-1]


def make_reverse_list_of_type_symbols(string):
    slist = make_list_of_type_symbols(string)
    slist.reverse()
    return slist


def make_list_of_type_symbols(string):
    string = remove_arrows(remove_colons(remove_curly_brackets(remove_round_brackets(string))))
    slist = string.split(' ')
    slist = list(filter(lambda a: a != '', slist))
    return slist


def remove_round_brackets(string):
    return string.replace(")", "").replace("(", "")


def remove_curly_brackets(string):
    return string.replace("{", "").replace("}", "")


def remove_arrows(string):
    return string.replace("→", "")


def remove_colons(string):
    return string.replace(":", "")


def has_equals(self, string):
    if string.find("=") > -1:
        return True
    return False


def has_colon(string):
    if string.find(":") > -1:
        return True
    return False


def eq_to_doteq(string):
    return string.replace("=", "≐")


def assert_questionmark(what):
    qmidx = what.find("?")
    if qmidx < 0:
        return "?" + what
    else:
        return what


def add_ods(string):
    objects = re.split(r'(\W)', string)
    onedel = False
    for i in range(2, len(objects)):
        if bool(re.match('[:=]', objects[i], re.I)):  # if it starts with : or =
            if onedel:
                objects[i] = "❘" + objects[i]
                return ''.join(objects)
            onedel = True  # start only at second : or =
    return ''.join(objects)


def functionize(string, typename="Ω", varname="x"):
    return string.replace("=", "= [ " + varname + " : " + typename + "]")


if __name__ == '__main__':
    Interview().cmdloop()
