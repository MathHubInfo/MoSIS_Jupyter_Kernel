**interview_kernel** is a Jupyter kernel using MetaKernel magics.

## Install

from this directory, run 
```shell
pip install .
python setup.py install
python -m interview_kernel.install
```

## Running

You can then run the interview_kernel kernel as a console, notebook, etc.:

```shell
jupyter console --kernel=interview_kernel
```

or 

```shell
jupyter notebook --kernel=interview_kernel
```

## MMT dependencies

You need to have a built version of http://mathhub.info/MitM/smglom/calculus/differentialequations 
and http://mathhub.info/MitM/smglom/calculus/differentialequations, which 
can be found in mathhub archives MitM/smglom and MitM/MoSIS, respectively.