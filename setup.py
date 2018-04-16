# cf. https://pypi.python.org/pypi/twine:
# $ python setup.py sdist bdist_wheel
# $ twine upload --repository-url https://test.pypi.org/legacy/ dist/*
# or
# $ twine upload --repository testpypi dist/*

from setuptools import setup

setup(
    name='interview_kernel',
    version='0.1.0',
    packages=['interview_kernel'],
    url='https://gl.kwarc.info/theresa_pollinger/MoSIS',
    license='MIT',
    author='Theresa Pollinger',
    author_email='theresa.pollinger@fau.de',
    description='A Jupyter kernel that interviews you for a PDE model and \
                    transforms it into an ExaStencils simulation.',
    python_requires=">=3.4",
    # replicating contents of MANIFEST,
    # cf.https://stackoverflow.com/questions/7522250/how-to-include-package-data-with-setuptools-distribute/14159430#14159430
    package_data={
        'interview_kernel': ['exastencils/compiler.jar',
                             'exastencils/generate_compile_and_run_list.sh',
                             'exastencils/lib/*.*'],
    },
#    data_files=[
#    ],
    zip_safe=False,
    # use_scm_version=True,
    setup_requires=['setuptools_scm'],  # or possibly https://pypi.python.org/pypi/setuptools-git
    install_requires=['transitions', 'bokeh', 'pandas', 'requests', 'pylatexenc', 'metakernel', 'lxml',
                      'IPython', 'jupyter_client', 'ipywidgets']
)
