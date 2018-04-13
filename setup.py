# cf. https://pypi.python.org/pypi/twine

from setuptools import setup

setup(
    name='interview_kernel',
    version='0.1.0',
    packages=['interview_kernel', 'interview_kernel/exastencils'],
    url='https://gl.kwarc.info/theresa_pollinger/MoSIS',
    license='MIT',
    author='Theresa Pollinger',
    author_email='theresa.pollinger@fau.de',
    description='A Jupyter kernel that interviews you for a PDE model and \
                    transforms it into an ExaStencils simulation.',
    python_requires=">=3.4",
    # replicating contents of MANIFEST, cf.
    package_data={
        'interview_kernel/exastencils': ['interview_kernel/exastencils/compiler.jar',
                                            'interview_kernel/exastencils/generate_compile_and_run_list.sh',
                                            'interview_kernel/exastencils/lib/*.*'],
    },
    # use_scm_version=True,
    setup_requires=['setuptools_scm'],
    install_requires=['transitions', 'bokeh', 'requests', 'pylatexenc', 'metakernel', 'lxml', 'IPython',
                      'jupyter_client', 'ipywidgets']
)
