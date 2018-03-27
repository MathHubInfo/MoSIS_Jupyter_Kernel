/*
cf.
https://github.com/jupyter/notebook/issues/1451
https://jupyter-notebook.readthedocs.io/en/latest/extending/frontend_extensions.html
to install (from shell): jupyter nbextension install preload.js --user
to enable (from shell): jupyter nbextension enable preload

TODO: Make it markup, 


do only if kernel_name == interview_kernel

so according to jupyter-book, we are making it a kernel.js now.
*/

define([
    'base/js/namespace'
], function(
    Jupyter
) {
    function onload() {
      if (Jupyter.notebook.get_cells().length===1){
        Jupyter.notebook.insert_cell_above('code', 0).set_text("pre-text");
      }
      console.log("interview kernel.js loaded")
    }
    return {
        onload: onload
    };
});

