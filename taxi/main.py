#!/usr/bin/env python
# All rights reserved.

from __future__ import print_function

import argparse
import logging
import os.path
import time

import raw2aws

from bokeh.plotting import figure
#from bokeh.palettes import Viridis6 as palette
from bokeh.palettes import GnBu6 as palette
from bokeh.layouts import row, column, layout, widgetbox
from bokeh.models import ColumnDataSource, HoverTool, Div, LogColorMapper, \
    FixedTicker, FuncTickFormatter
from bokeh.models.widgets import Button, Dropdown, RadioButtonGroup, Toggle, Select
from bokeh.models.renderers import GlyphRenderer
from bokeh.io import curdoc

from common import *
from geo import NYCBorough, NYCGeoPolygon
from mapred import StatDB
from tasks import TaskManager

logging.basicConfig()

def parse_argv():
    o = Options()
    o.add('--purge', dest='purge', action='store_true', default=False,
        help='purge data before load')
    return o.load()

class InteractivePlot:
    def __init__(self, opts):
        self.db = StatDB(opts)
        if opts.purge: self.db.purge()

        self.data = None
        self.last_query = {
            'timestamp': 0.0,
                'color': '',
                 'year': 0,
                'month': 0
        }

        self.tasks = TaskManager(opts)

        self.districts = None
        self.districts_xs = []
        self.districts_ys = []
        self.districts_names = []

        self.selected_type = 'Pickups'
        self.selected_borough = 0
        self.selected_color = 'green'
        self.selected_year = 2016
        self.selected_month = 1
        self.refresh_ticks = 0

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(opts.verbose)

    def query(self, color, year, month):
        if time.time() - self.last_query['timestamp'] < 2: return

        year, mont = int(year), int(month)
        self.data = self.db.get(color, year, month)
        self.last_query['color'] = color
        self.last_query['year'] = year
        self.last_query['month'] = month
        self.last_query['timestamp'] = time.time()

    def hot_map_init(self, width=700, height=700, webgl=True):
        self.districts = NYCGeoPolygon.load_districts()

        rates = []
        for district in self.districts:
            x, y = district.xy()
            self.districts_xs.append(x)
            self.districts_ys.append(y)
            self.districts_names.append(district.name)
            rates.append(self.data.pickups[district.index]) # default uses pickups

        self.hot_map_source = ColumnDataSource(data=dict(
            x=self.districts_xs,
            y=self.districts_ys,
            name=self.districts_names,
            rate=rates,
        ))

        palette.reverse()
        color_mapper = LogColorMapper(palette=palette)

        self.hot_map = figure(webgl=webgl,
            plot_height=height, plot_width=width,
            tools='pan,wheel_zoom,box_zoom,reset,hover,save',
            x_axis_location=None, y_axis_location=None
        )
        self.hot_map.grid.grid_line_color = None

        self.hot_map.patches('x', 'y', source=self.hot_map_source,
            fill_color={'field': 'rate', 'transform': color_mapper},
            fill_alpha=0.7, line_color="white", line_width=0.5)
        self.hot_map.title.text = "%s %s/%s, %s" % \
                (self.selected_type,
                 self.selected_year, self.selected_month,
                 NYCBorough.BOROUGHS[self.selected_borough])

        hover = self.hot_map.select_one(HoverTool)
        hover.point_policy = "follow_mouse"
        hover.tooltips = [
            ("District", "@name"),
            ("Trips", "@rate"),
            ("Coordinates", "($x, $y)"),
        ]

    def hot_map_update(self):
        rates = []
        for district in self.districts:
            rate = 0
            borough = self.selected_borough
            if borough == 0 or borough == district.region:
                if self.selected_type == 'Pickups':
                    rate = self.data.pickups[district.index]
                else:
                    rate = self.data.dropoffs[district.index]
            rates.append(rate)

        self.hot_map_source.data=dict(
            x=self.districts_xs,
            y=self.districts_ys,
            name=self.districts_names,
            rate=rates,
        )
        self.hot_map.title.text = "%s %s/%s, %s" % \
                (self.selected_type,
                 self.selected_year, self.selected_month,
                 NYCBorough.BOROUGHS[self.selected_borough])

    def trip_hour_init(self, width=620, height=350, webgl=True):
        self.trip_hour = figure(webgl=webgl, toolbar_location=None,
            width=width, height=height, title='Hour')
        self.trip_hour_source = ColumnDataSource(data=dict(
            x=range(24), hour=self.data.get_hour()))
        vbar = self.trip_hour.vbar(width=0.6, bottom=0, x='x', top='hour',
                source=self.trip_hour_source, fill_alpha=0.7,
            line_color="white", color='#D35400')
        self.trip_hour.y_range.start = 0
        self.trip_hour.xaxis.major_tick_line_color = None
        self.trip_hour.xaxis.minor_tick_line_color = None
        self.trip_hour.xaxis.ticker=FixedTicker(ticks=range(24))

        self.trip_hour.select(dict(type=GlyphRenderer))
        self.trip_hour.add_tools(HoverTool(renderers=[vbar],
            tooltips=[("Trips", "@hour")]))

    def trip_hour_update(self):
        self.trip_hour_source.data=dict(x=range(24), hour=self.data.get_hour())

    def trip_distance_init(self, width=310, height=350, webgl=True):
        def ticker():
            labels = {0: '0~1', 1: '1~2', 2: '2~5', 3: '5~10', 4: '10~20', 5: '>20'}
            return labels[tick]

        self.trip_distance = figure(webgl=webgl, toolbar_location=None,
            width=width, height=height, title='Distance (miles)')
        self.trip_distance_source = ColumnDataSource(data=dict(
            x=range(6), dist=self.data.get_distance()))
        vbar = self.trip_distance.vbar(width=1, bottom=0, x='x', top='dist',
            source=self.trip_distance_source, fill_alpha=0.7,
            line_color="white", color='#588c7e')
        self.trip_distance.y_range.start = 0
        self.trip_distance.xaxis.major_tick_line_color = None
        self.trip_distance.xaxis.minor_tick_line_color = None
        self.trip_distance.xaxis.formatter=FuncTickFormatter.from_py_func(ticker)

        self.trip_distance.select(dict(type=GlyphRenderer))
        self.trip_distance.add_tools(HoverTool(renderers=[vbar],
            tooltips=[("Trips", "@dist")]))

    def trip_distance_update(self):
        self.trip_distance_source.data=dict(x=range(6), dist=self.data.get_distance())

    def trip_fare_init(self, width=310, height=350, webgl=True):
        def ticker():
            labels = {0: '0~5', 1: '5~10', 2: '10~25', 3: '25~50', 4: '50~100', 5: '>100'}
            return labels[tick]

        self.trip_fare = figure(webgl=webgl, toolbar_location=None,
            width=width, height=height, title='Fare (US dolloars)')
        self.trip_fare_source = ColumnDataSource(data=dict(
            x=range(6), fare=self.data.get_fare()))
        vbar = self.trip_fare.vbar(width=1, bottom=0, x='x', top='fare',
            source=self.trip_fare_source, fill_alpha=0.7,
            line_color="white", color='#ffcc5c')
        self.trip_fare.y_range.start = 0
        self.trip_fare.xaxis.major_tick_line_color = None
        self.trip_fare.xaxis.minor_tick_line_color = None
        self.trip_fare.xaxis.formatter=FuncTickFormatter.from_py_func(ticker)

        self.trip_fare.select(dict(type=GlyphRenderer))
        self.trip_fare.add_tools(HoverTool(renderers=[vbar],
            tooltips=[("Trips", "@fare")]))

    def trip_fare_update(self):
        self.trip_fare_source.data=dict(x=range(6), fare=self.data.get_fare())

    def resource_usage_init(self, width=740, height=120):
        data_len = 4
        self.resource_usage_source = ColumnDataSource(data=dict(
              x=[0, 1, 2, 3, 4],
            cpu=[2, 3, 5, 4, 10],
            mem=[20, 10, 40, 30, 15]
        ))
        self.resource_usage = figure(plot_width=width, plot_height=height,
            toolbar_location=None, title=None,
            x_axis_label='Elapsed (seconds)', y_axis_label='%')

        self.resource_usage.line(x='x', y='cpu',color='firebrick', legend='CPU',
            line_alpha=0.8, line_width=2,
            source=self.resource_usage_source)
        self.resource_usage.line(x='x', y='mem', color='dodgerblue', legend='MEM',
            line_alpha=0.8, line_width=2,
            source=self.resource_usage_source)

        self.resource_usage.xgrid.visible = False
        self.resource_usage.ygrid.visible = False
        self.resource_usage.x_range.start = 0
        self.resource_usage.x_range.end = data_len * 1.07
        self.resource_usage.y_range.start = 0

    def tasks_stat_init(self, width=740, height=120):
        self.tasks_stat_tick = 1
        remain, retry = self.tasks.count_tasks()
        self.tasks_stat_source = ColumnDataSource(data=dict(
              x=range(self.tasks_stat_tick),
              remain=[remain], retry=[retry]
        ))
        self.tasks_stat = figure(plot_width=width, plot_height=height,
            title=None, toolbar_location=None,
            x_axis_label='elapsed (seconds)', y_axis_label='tasks')

        self.tasks_stat.line(x='x', y='remain',color='firebrick',
            line_alpha=0.8, line_width=2,
            legend='Remain', source=self.tasks_stat_source)
        self.tasks_stat.line(x='x', y='retry', color='dodgerblue',
            line_alpha=0.8, line_width=2,
            legend='Retry', source=self.tasks_stat_source)
        self.tasks_stat.legend.location = "bottom_left"

        self.tasks_stat.xgrid.visible = False
        self.tasks_stat.ygrid.visible = False
        self.tasks_stat.x_range.start = 0
        self.tasks_stat.y_range.start = 0

    def tasks_stat_update(self):
        self.tasks_stat_tick += 1
        rm, re = self.tasks.count_tasks()
        self.tasks_stat_source.data['remain'].append(rm)
        self.tasks_stat_source.data['retry'].append(re)
        self.tasks_stat_source.data = dict(
              x=range(self.tasks_stat_tick),
              remain=self.tasks_stat_source.data['remain'],
              retry=self.tasks_stat_source.data['retry']
        )

    def plot(self):
        def update():
            self.refresh_ticks += 1
            self.query(self.selected_color, self.selected_year, self.selected_month)

            self.hot_map_update()
            self.trip_hour_update()
            self.trip_distance_update()
            self.trip_fare_update()
            self.tasks_stat_update()
            # self.resource_usage_update()

        def on_select():
            BOROUGHS_CODE = {v: k for k, v in NYCBorough.BOROUGHS.items()}
            self.selected_color = 'green' if color.active == 1 else 'yellow'
            pickup.label = 'Pickups' if pickup.active else 'Dropoffs'
            self.selected_type = pickup.label
            self.selected_borough = BOROUGHS_CODE[borough.value]
            borough.label = borough.value
            self.selected_year = int(year.value)
            self.selected_month = int(month.value)

        def on_submit():
            self.logger.debug('submit (%s, %s, %s, %s, %s)' % \
                (self.selected_type,
                 NYCBorough.BOROUGHS[self.selected_borough],
                 self.selected_color,
                 self.selected_year, self.selected_month))
            self.tasks.create_tasks(
                self.selected_color,
                self.selected_year,
                self.selected_month)

        cwd = os.path.dirname(__file__)
        desc = Div(text=open(
            os.path.join(cwd, "description.html")).read(), width=1000)

        # Create input controls
        color = RadioButtonGroup(labels=['Yellow', 'Green'], active=1)
        color.on_change('active', lambda attr, old, new: on_select())

        pickup = Toggle(label='Pickups', button_type="primary", active=True)
        pickup.on_change('active', lambda attr, old, new: on_select())

        # BUG: Dropdown menu value cannot be integer, i.e., ('Mahattan', '1')
        borough_menu = [('All Boroughs', 'All Boroughs'), None,
            ('Manhattan', 'Manhattan'), ('Bronx', 'Bronx'), ('Brooklyn', 'Brooklyn'),
            ('Queens', 'Queens'), ('Staten Island', 'Staten Island')]
        # https://github.com/bokeh/bokeh/issues/4915
        borough = Dropdown(label="Boroughs", button_type="warning",
            menu=borough_menu, value='All Boroughs')
        borough.on_change('value', lambda attr, old, new: on_select())

        year = Select(title="Year:", value=str(self.selected_year),
            options=[str(y) for y in range(MIN_DATE['green'].year, MAX_DATE['green'].year+1)])
        year.on_change('value', lambda attr, old, new: on_select())

        month = Select(title="Month:", value=str(self.selected_month),
            options=[str(m) for m in range(1, 13)])
        month.on_change('value', lambda attr, old, new: on_select())

        submit = Button(label="Submit", button_type="success")
        submit.on_click(on_submit)

        controls = [color, pickup, borough, year, month, submit]

        self.query(self.selected_color, self.selected_year, self.selected_month)
        self.hot_map_init()
        self.trip_hour_init()
        self.trip_distance_init()
        self.trip_fare_init()
        self.tasks_stat_init()
        self.resource_usage_init()

        rightdown_row = row([self.trip_distance, self.trip_fare])
        right_column = column([self.trip_hour, rightdown_row])
        inputs = widgetbox(*controls, width=140, sizing_mode="fixed")
        l = layout([
            [desc],
            [inputs, self.hot_map, right_column],
            [self.tasks_stat, self.resource_usage],
        ], sizing_mode="fixed")

        curdoc().add_root(l)
        curdoc().add_periodic_callback(update, 5000)
        curdoc().title = "NYC Taxi Data Explorer"

if __name__ == "__main__":
    print("usage: bokeh serve --show %s --args [ARGS]" % os.path.dirname(__file__))
else:
    p = InteractivePlot(parse_argv())
    p.plot()
