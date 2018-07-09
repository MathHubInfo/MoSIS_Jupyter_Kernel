import ipywidgets as widgets
import numpy as np
import matplotlib.pyplot as plt
import math

from beakerx import *
import pandas as pd

from inspect import signature

class WidgetFactory:

    # value=[5, 7.5],
    # min=0,
    # max=10.0,
    # step=0.1,
    # description='Test:',
    # disabled=False,
    # continuous_update=False,
    # orientation='horizontal',
    # readout=True,
    # readout_format='.1f',


    def createFloatRangeSlider(self, value = [0.0,1.0] ,min = 0.0, max = 1.0, step = 0.1,
        description = '', disabled = False, orientation = 'horizontal', readout = True,
        readout_format = '.1f',continuous_update = True):
        slider = widgets.FloatRangeSlider(value = value,min = min,max = max,step = step,description = description,
            orientation = orientation,readout = readout,readout_format = readout_format)
        slider.continuous_update = continuous_update
        return slider

    """ creates a ToggleButton widget. Defaults to a 'Yes'-'No' selection widget"""
    def createToggleButtons(self,options = ['Yes','No'], disabled = False,button_style =''):
        return widgets.ToggleButtons(options = options,disabled = disabled,button_style = button_style)


    def createPlot(self, f, description = 'Plot', start = 0, stop = 20, points = 100, logPlot = False, logBase = 10):
        sig = signature(f)
        params = sig.parameters

        sliders = []
        
        ypts = []
        xpts = np.linspace(start = start,stop = stop,num = points,endpoint = True)
        for i in range(0, points):
            ypts.append(f(xpts[i]))

        plot = Plot(title= description, yLabel= '')
        line = Line(x= xpts, y= ypts, displayName= f.__name__+str(sig))
        plot.add(line)


        # TODO pls clean me up!
        def updatePlot(dict):
            sypts = []
            slider = dict['owner']
            args = {}
            displayName = f.__name__+'('
            for s in slider.plot.sliders:
                args.update({s.variable : s.value})
                displayName += str(s.variable)+"= "+str(s.value)+", "
            displayName = displayName[:-1] + ')'

            # **{keyword : value}
            for i in range(0, points):
                sypts.append(f(xpts[i],**args))

            # TODO this here needs to only delete the one line that should be updated and not all of them
            slider.plot.chart.graphics_list = []
            slider.plot.add(Line(x = xpts,y = sypts, displayName= displayName))

        for key in params:
            if key != 'x':
                slider = widgets.IntSlider(description = key)
                slider.plot = plot
                slider.variable = key
                slider.observe(updatePlot,'value')
                sliders.append(slider)
                display(slider)
        
        plot.sliders = sliders


        return plot

