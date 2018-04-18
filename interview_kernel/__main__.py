from ipykernel.kernelapp import IPKernelApp
from .interview_kernel import Interview

IPKernelApp.launch_instance(kernel_class=Interview)
