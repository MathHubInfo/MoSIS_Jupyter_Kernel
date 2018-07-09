**interview_kernel** is a Jupyter kernel using MetaKernel magics.

## Install

from this directory, run 
```shell
pip install .
python setup.py install
python -m interview_kernel.install
```

## Running

You can then run the interview_kernel kernel as a notebook:

```shell
jupyter notebook --kernel=interview_kernel
```

## MMT dependencies

You need to have a built version of http://mathhub.info/MitM/smglom 
and http://mathhub.info/MitM/smglom/calculus/differentialequations namespaces, which 
can be found in mathhub archives 
`MitM/smglom` and 
`MitM/MoSIS`, respectively.

To start the server in the MMT Shell::

    server on 9000
    extension info.kwarc.mmt.interviews.InterviewServer
    extension info.kwarc.mmt.api.ontology.RelationalReader
