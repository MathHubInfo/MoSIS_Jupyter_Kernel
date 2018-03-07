
import os
from pathlib import Path
from collections import OrderedDict
from pylatexenc.latexencode import utf8tolatex, utf82latex


def remove_ensuremaths():
    thisdict = utf82latex
    for key, value in utf82latex.items():
        if value.startswith('\\ensuremath{'):
            utf82latex[key] = value.replace('\\ensuremath{', '', 1)[:-1]

    # from here on we are concerned with the creation of output


class ExaOutput:
    def __init__(self):
        remove_ensuremaths()

    def create_output(self, simdata):
        self.filespathpre = "Configs"  # just to build paths, remove
        self.probname = "Poisson_1D"  # just to build paths, remove
        #output parameters which should also be made adaptable at some point
#        self.knowledge = OrderedDict([
#                           ("dimensionality" , simdata["num_dimensions"]),
#                           ("minLevel" , 1),
#                           ("maxLevel" , 7),
#                           ("discr_type" , simdata["sim_type"]),
#                           ("l3tmp_generateL4" , False),
#                           ("experimental_layerExtension" , True)
#                           ])
        self.platform = OrderedDict([
                            ("targetOS" , "Linux"),
                           ("targetCompiler" , "GCC"),
                           ("targetCompilerVersion" , 5),
                           ("targetCompilerVersionMinor" , 4),
                           ("simd_instructionSet" , "AVX")
                           ])
        self.settings = OrderedDict([
            ("user", "Guest"),
            ("configName", "1D_FD_Poisson_fromL1"),
            ("basePathPrefix", "./Poisson"),
            ("l1file", "\"$configName$.exa1\""),
            ("debugL1File", "\"../Debug/$configName$_debug.exa1\""),
            ("debugL2File", "\"../Debug/$configName$_debug.exa2\""),
            ("debugL3File", "\"../Debug/$configName$_debug.exa3\""),
            ("debugL4File", "\"../Debug/$configName$_debug.exa4\""),
            ("htmlLogFile", "../Debug/$configName$_log.html"),
            ("outputPath", "../generated/$configName$/"),
            ("produceHtmlLog", "true"),
            ("timeStrategies", "true"),
            ("buildfileGenerators", "{ \"MakefileGenerator\" }")
        ])
        filespath = Path(self.filespathpre).joinpath(self.settings["user"]).joinpath(self.probname)
        self.l1file = filespath.with_suffix('.exa1')
        self.l2file = filespath.with_suffix('.exa2')
        self.l3file = filespath.with_suffix('.exa3')
        self.l4file = filespath.with_suffix('.exa4')
        ff = str(Path(self.settings["basePathPrefix"]).joinpath(self.filespathpre).joinpath(self.settings["user"]))
        if not os.path.exists(ff):
            try:
                os.makedirs(ff)
            except OSError as exc:# Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise

        self.create_settings()
#        self.create_platform()
        self.create_knowledge()
        self.create_l1(simdata)
#        self.create_l2(simdata)
#        self.create_l3()
#        self.create_l4()

    def create_l1(self, simdata):
        l1path = str(Path(self.settings["basePathPrefix"]).joinpath(self.l1file))
        domain_name = utf8tolatex(simdata["domain"]["name"], non_ascii_only=True, brackets=False)
        op = utf8tolatex(simdata["pdes"]["pdes"][-1]["op"], non_ascii_only=True, brackets=False)
        bcrhs = self.replace_boundary_x(simdata["bcs"]["bcs"][-1]["rhsstring_expanded"]) #TODO expand
        pderhs = simdata["pdes"]["pdes"][-1]["rhsstring_expanded"]
        with open(l1path, 'w') as l1:
            l1.write(
                "/// inline knowledge \n"
                "Knowledge { \n"
                "  dimensionality = " + str(simdata["num_dimensions"]) + " \n" 
                " \n"
                "  minLevel       = 5 \n"
                "  maxLevel       = 15 \n"
                "} \n"
                " \n"
                "/// problem specification \n"
                " \n"
                "Domain \Omega = ( " + str(simdata["domain"]["from"]) + ", " + str(simdata["domain"]["to"]) + " ) \n" 
                " \n"
                "Field f@finest \in \Omega = " + pderhs + " \n" 
                "Field u \in \Omega = 0.0 \n" 
                " \n"
                "Field u@finest \in \partial \Omega = " + bcrhs + " \n" #"sin ( 0.5 * PI * vf_boundaryCoord_x ) \n" #TODO expand
                "Field u@(all but finest) \in \partial \Omega = 0.0 \n"
                " \n"
                "Operator op = " + op + " // alt: - \partial_{xx} \n" 
                " \n"
                "Equation uEq@finest           op * u == f \n" #insert pde
                "Equation uEq@(all but finest) op * u == 0.0 \n"
                " \n"
                "/// configuration of inter-layer transformations \n"
                " \n"
                "DiscretizationHints { // alt: Discretize, L2Hint(s) \n"
                "  f on Node \n"
                "  u on Node \n"
                " \n"
                "  op on \Omega \n"
                " \n"
                "  uEq \n"
                " \n"
                "  // paramters \n"
                "  discr_type = \"" + simdata["sim"]["type"] + "\" \n"
                "} \n"
                " \n"
                "SolverHints { // alt: Solve, L3Hint(s) \n"
                "  generate solver for u in uEq \n"
                " \n"
                "  // parameters \n"
                "  solver_targetResReduction = 1e-6 \n"
                "} \n"
                " \n"
                "ApplicationHints { // alt L4Hint(s) \n"
                "  // parameters \n"
                "  l4_genDefaultApplication = true \n"
                "} \n"
           )

    def replace_x(self, string):
        return string.replace("x", "vf_nodePosition_x")

    def replace_boundary_x(self, string):
        return string.replace("x", "vf_boundaryCoord_x")

    def create_l2(self, simdata):
        l2path = str(Path(self.settings["basePathPrefix"]).joinpath(self.l2file))
        with open(l2path,'w') as l2:
            l2.write(
                "Domain global< " + simdata["domain"]["from"] + " to " + simdata["domain"]["to"] + " > \n" # TODO domain goes here
                "\n"
                "Field Solution with Real on Node of global = 0.0 \n" #TODO codomain goes here
                "Field Solution@finest on boundary = vf_boundaryCoord_x ** 2 \n" # TODO BCs go here
                "Field Solution@(all but finest) on boundary = 0.0 \n"
                "\n"
                "Field RHS with Real on Node of global = 0.0 \n" #TODO RHS goes here
                #"Operator Laplace from kron ( Laplace_1D, Laplace_1D ) \n"
                "Operator Laplace_1D from Stencil { \n"
                "   [ 0] => 2.0 / ( vf_gridWidth_x ** 2 ) \n"
                "   [-1] => -1.0 / ( vf_gridWidth_x ** 2 ) \n"
                "   [ 1] => -1.0 / ( vf_gridWidth_x ** 2 ) \n"
                "\n"
                "Equation solEq@finest { \n"
                "    Laplace_1D * Solution == RHS \n"
                "} \n"
                "\n"
                "Equation solEq@(all but finest) { \n"
                "    Laplace_1D * Solution == 0.0 \n"
                "} \n"
            )

    def create_l3(self):
        l3path = str(Path(self.settings["basePathPrefix"]).joinpath(self.l3file))
        with open(l3path,'w') as l3:
            l3.write(
                "generate solver for Solution in solEq \n"
            )

    def create_l4(self):
        l4path = str(Path(self.settings["basePathPrefix"]).joinpath(self.l4file))
        with open(l4path,'w') as l4:
            l4.write(
                "Function Application ( ) : Unit { \n"
                "   startTimer ( 'setup' ) \n"
                "\n"
                "   initGlobals ( ) \n"
                "   initDomain ( ) \n"
                "   initFieldsWithZero ( ) \n"
                "   initGeometry ( ) \n"
                "   InitFields ( ) \n"
                "\n"
                "   stopTimer ( 'setup' ) \n"
                "\n"
                "   startTimer ( 'solve' ) \n"
                "\n"
                "   Solve@finest ( ) \n"
                "\n"
                "   stopTimer ( 'solve' ) \n"
                "\n"
                "   printAllTimers ( ) \n"
                "\n"
                "   destroyGlobals ( ) \n"
                "} \n"
            )

    def key_val(self, key, val):
        return key.ljust(30) + ' = ' + val + '\n'

    def format_key_val(self, key, val):
        return self.key_val(key, repr(val).replace('\'', '\"'))

    def format_key(self, key, dict):
        return self.format_key_val(key, dict[key])

    def create_settings(self):
        settingspath = str(Path(self.settings["basePathPrefix"]).joinpath('settings'))
        with open(settingspath,'w') as settingsfile:
            for key in self.settings:
                settingsfile.write(self.format_key(key, self.settings))

    def create_platform(self):
        platformpath = str(Path(self.settings["basePathPrefix"]).joinpath('platform'))
        with open(platformpath,'w') as platformfile:
            for key in self.platform:
                platformfile.write(self.format_key(key, self.platform))

    def create_knowledge(self):
        knowledgepath = str(Path(self.settings["basePathPrefix"]).joinpath('knowledge'))
        with open(knowledgepath,'w') as knowledgefile:
#            for key in self.knowledge:
#                knowledgefile.write(self.format_key(key, self.knowledge))
            knowledgefile.write(
                "// omp parallelization on exactly one fragment in one block \n"
                "import '../lib/domain_onePatch.knowledge' \n"
                "import '../lib/parallelization_pureOmp.knowledge'"
            )
