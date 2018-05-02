
import os
from pathlib import Path
from tempfile import gettempdir
import subprocess
from collections import OrderedDict
from pylatexenc.latexencode import utf8tolatex, utf82latex


def remove_ensuremaths():
    """remove ensuremath wrappers in utf82latex before translating back from unicode to latex"""
    for key, value in utf82latex.items():
        if value.startswith('\\ensuremath{'):
            utf82latex[key] = value.replace('\\ensuremath{', '', 1)[:-1]


class ExaOutput:
    """generates configuration files for exastencils,
        but only if simdata is given"""
    def __init__(self, simdata=None, username="user", probname=None):
        remove_ensuremaths()
        self.exastencils_path = Path.home().joinpath("./exastencils")

        self.username = username

        if probname is None:
            self.probname = self.username
        else:
            self.probname = probname

        #output parameters which should also be made adaptable at some point
        self.platform = OrderedDict([
                            ("targetOS", "Linux"),
                           ("targetCompiler", "GCC"),
                           ("targetCompilerVersion", 5),
                           ("targetCompilerVersionMinor", 4),
                           ("simd_instructionSet", "AVX")
                           ])
        self.settings = OrderedDict([
            ("user", self.username),
            ("configName", self.probname),
            ("basePathPrefix", "./" + self.probname),
            ("l1file", "$configName$.exa1"),
            ("debugL1File", "../Debug/$configName$_debug.exa1"),
            ("debugL2File", "../Debug/$configName$_debug.exa2"),
            ("debugL3File", "../Debug/$configName$_debug.exa3"),
            ("debugL4File", "../Debug/$configName$_debug.exa4"),
            ("htmlLogFile", "../Debug/$configName$_log.html"),
            ("outputPath", "../generated/$configName$/"),
            ("produceHtmlLog", True),
            ("timeStrategies", True),
            ("buildfileGenerators", "{ \"MakefileGenerator\" }")
        ])
        self.tmppath = Path(gettempdir())
        self.dirpath = self.exastencils_path.joinpath(self.probname)
        self.filespath = self.dirpath.joinpath(self.probname)
        ff = [self.dirpath]  # , self.tmppath.joinpath("generated"), self.tmppath.joinpath("Debug")]
        for f in ff:
            if not os.path.exists(str(f)):
                try:
                    os.makedirs(str(f))
                except OSError as exc:# Guard against race condition
                    if exc.errno != errno.EEXIST:
                        raise
            # # and link it into the exastencils directory
            # os.symlink(str(f), str(self.exastencils_path.joinpath(os.path.basename(os.path.normpath(f)))))
        if simdata is not None:
            self.create_settings()
    #        self.create_platform()
            self.create_knowledge()
            self.create_l1(simdata)
            self.create_examples_list_file()
    #        self.create_l2(simdata)
    #        self.create_l3()
    #        self.create_l4()

    def create_l1(self, simdata):
        l1path = str(self.filespath.with_suffix('.exa1'))
        domain_name = utf8tolatex(simdata["domain"]["name"], non_ascii_only=True, brackets=False)
        op = utf8tolatex(simdata["pdes"]["pdes"][-1]["op"], non_ascii_only=True, brackets=False)
        bc_rhs = self.replace_cdot(self.replace_boundary_x(simdata["bcs"]["bcs"][-1]["rhsstring_expanded"])) #TODO expand
        pde_rhs = self.replace_x(self.replace_cdot(simdata["pdes"]["pdes"][-1]["rhsstring_expanded"]))
        unknowns = [*simdata["unknowns"]]
        first_unknown = unknowns[0]
        self.l1_string = str(
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
                "Field f@finest \in \Omega = " + pde_rhs + " \n"
                "Field " + first_unknown + " \in \Omega = 0.0 \n"
                " \n"
                "Field " + first_unknown + "@finest \in \partial \Omega = " + bc_rhs + " \n" #"sin ( 0.5 * PI * vf_boundaryCoord_x ) \n" #TODO expand
                "Field " + first_unknown + "@(all but finest) \in \partial \Omega = 0.0 \n"
                " \n"
                "Operator op = " + op + " // alt: - \partial_{xx} \n"
                " \n"
                "Equation " + first_unknown + "Eq@finest           op * " + first_unknown + " == f \n" #insert pde
                "Equation " + first_unknown + "Eq@(all but finest) op * " + first_unknown + " == 0.0 \n"
                " \n"
                "/// configuration of inter-layer transformations \n"
                " \n"
                "DiscretizationHints { // alt: Discretize, L2Hint(s) \n"
                "  f on Node \n"
                "  " + first_unknown + " on Node \n"
                " \n"
                "  op on \Omega \n"
                " \n"
                "  " + first_unknown + "Eq \n"
                " \n"
                "  // paramters \n"
                "  discr_type = \"" + simdata["sim"]["type"] + "\" \n"
                "} \n"
                " \n"
                "SolverHints { // alt: Solve, L3Hint(s) \n"
                "  generate solver for " + first_unknown + " in " + first_unknown + "Eq \n"
                " \n"
                "  // parameters \n"
                "  solver_targetResReduction = 1e-6 \n"
                "} \n"
                " \n"
                "ApplicationHints { // alt L4Hint(s) \n"
                "  // parameters \n"
                "  l4_genDefaultApplication = true \n"
                "  l4_defAppl_FieldToPrint = \"" + first_unknown + "\" \n" #TODO
                "} \n")
        with open(l1path, 'w') as l1:
            l1.write(self.l1_string)

    def replace_x(self, string):
        return string.replace("x", "vf_nodePosition_x@current")

    def replace_cdot(self, string):
        return string.replace("⋅", "*")

    def replace_boundary_x(self, string):
        return string.replace("x", "vf_boundaryCoord_x")

    def create_l2(self, simdata):
        l2path = str(self.filespath.with_suffix('.exa2'))
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
        l3path = str(self.filespath.with_suffix('.exa3'))
        with open(l3path, 'w') as l3:
            l3.write(
                "generate solver for Solution in solEq \n"
            )

    def create_l4(self):
        l4path = str(self.filespath.with_suffix('.exa4'))
        with open(l4path, 'w') as l4:
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
        val_repr = repr(val).replace('\'', '\"')
        if isinstance(val, bool):
            val_repr = val_repr.lower()
        return self.key_val(key, val_repr)

    def format_key(self, key, dict):
        return self.format_key_val(key, dict[key])

    def create_settings(self):
        settingspath = str(self.filespath) + '.settings'
        with open(settingspath, 'w') as settingsfile:
            for key in self.settings:
                if key == "buildfileGenerators":
                    settingsfile.write(self.key_val(key, self.settings[key]))
                else:
                    settingsfile.write(self.format_key(key, self.settings))

    def create_platform(self):
        platformpath = str(self.filespath) + '.platform'
        with open(platformpath, 'w') as platformfile:
            for key in self.platform:
                platformfile.write(self.format_key(key, self.platform))

    def create_knowledge(self):
        knowledgepath = str(self.filespath) + '.knowledge'
        with open(knowledgepath, 'w') as knowledgefile:
#            for key in self.knowledge:
#                knowledgefile.write(self.format_key(key, self.knowledge))
            knowledgefile.write(
                "// omp parallelization on exactly one fragment in one block \n"
                "import '../lib/domain_onePatch.knowledge' \n"
                "import '../lib/parallelization_pureOmp.knowledge'"
            )

    def create_examples_list_file(self):
        examples_path = str(self.exastencils_path.joinpath("examples").with_suffix('.sh'))
        with open(examples_path, 'w') as shell_file:
            shell_file.write(
                "#!/usr/bin/env bash \n"\
                "\n"
                "\n"
                "configList=\"\" \n"\
                "configList+=\"{}/{} \" \n".format(self.probname, self.probname)) #(self.dirpath, self.probname))

class ExaRunner:
    """A class to run exastencils using the files generated by an Exaoutput class, and to get the results"""

    from functools import lru_cache

    def __init__(self, exaout):
        self.exaout = exaout

    def run_exastencils(self):
        # print(str(os.path.abspath(self.exaout.exastencils_path)))
        p = subprocess.run(["./generate_compile_and_run_list.sh"], cwd=str(self.exaout.exastencils_path),
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.stdout
        if p.returncode != 0:
            print(out)

    @lru_cache()
    def load_data(self, data_name="u"):  # TODO more dimensions
        import pandas as pd
        data_path = self.exaout.exastencils_path.joinpath("generated").joinpath(self.exaout.probname)\
                                                .joinpath(data_name).with_suffix(".dat")
        df = pd.read_csv(data_path, sep=' ', index_col=0)
        try:
            df.columns = [data_name]
        except ValueError:  # length mismatch because additional column of nans was read
            df.columns = [data_name, 'nan']
        return df
