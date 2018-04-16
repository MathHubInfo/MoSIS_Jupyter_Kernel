**MetaKernel Echo** is a Jupyter kernel using MetaKernel magics, shell, help, and parallel processing tools. This code provides an example MetaKernel kernel.

## Install

First, you need to install the metakernel_echo library and dependencies:

```shell
pip install interview_kernel --upgrade
```

Then, you need to install the metakernel echo kernel spec:

```shell
python interview_kernel install
```

## Running

You can then run the interview_kernel kernel as a console, notebook, etc.:

```shell
jupyter console --kernel=interview_kernel
```

## Dependencies

1. IPython 3
1. MetaKernel (installed with pip)
