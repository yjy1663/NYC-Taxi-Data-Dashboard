#!/usr/bin/env python
# All rights reserved.

# Geo Location Processing

from __future__ import print_function

import json
import os.path
import sys

import shapely.geometry

from collections import OrderedDict

class NYCBorough:
    BOROUGHS = OrderedDict({
        0: 'All Boroughs',
        1: 'Manhattan',
        2: 'Bronx',
        3: 'Brooklyn',
        4: 'Queens',
        5: 'Staten Island'
    })

    CENTERS = OrderedDict({
        1: shapely.geometry.Point(-73.965527, 40.782966), # Central Park
        2: shapely.geometry.Point(-73.877636, 40.851236), # Bronx Zoo
        3: shapely.geometry.Point(-73.951279, 40.631111), # Brooklyn College
        4: shapely.geometry.Point(-73.796699, 40.725518), # St. John's Univ.
        5: shapely.geometry.Point(-74.148280, 40.605389), # CUNY College
    })

    @classmethod
    def in_which(cls, longitude, latitude):
        min_distance = sys.maxint
        min_borough = 1
        for idx, center in cls.CENTERS.items():
            d = center.distance(shapely.geometry.Point(longitude, latitude))
            if d < min_distance:
                min_distance = d
                min_borough = idx
        return min_borough

class NYCGeoPolygon:
    NYC_DISTRICTS_JSON = 'nyc_community_districts.geojson'
    NYC_BOROUGHS_JSON  = 'nyc_boroughs.geojson'

    def __init__(self, index, name, polygon):
        self.index = index
        self.name = name
        self.polygon = shapely.geometry.shape(polygon)
        self.region = index / 10000

    def __contains__(self, point):
        return self.polygon.contains(shapely.geometry.Point(point))

    def __str__(self):
        return '{index}: {name}'.format(**self.__dict__)

    def xy(self):
        x, y = self.polygon.exterior.coords.xy
        return list(x), list(y)

    @classmethod
    def load(cls, filename):
        polygons = []
        with open(filename, 'r') as f:
            for feature in json.load(f)['features']:
                properties = feature['properties']
                if 'boro_name' in properties:
                    # Boroughs
                    name = properties['boro_name']
                    index = int(properties['boro_code']) * 10000
                else:
                    # Community districts
                    name = 'Community District %s' % properties['boro_cd']
                    index = int(properties['boro_cd']) * 100

                # Flatten multipolygon
                # see structure at http://terraformer.io/glossary/
                geometry = feature['geometry']
                if geometry['type'].lower() == 'polygon':
                    raise NotImplementedError
                for i, coords in enumerate(geometry['coordinates']):
                    polygon = {'type': 'Polygon', 'coordinates': coords}
                    polygons.append(NYCGeoPolygon(index + i + 1, name, polygon))

        # Important: sort districts by the propabilities of high trip count
        def shift_borough(district):
            if district.region == 2: return 4
            if district.region == 4: return 2
            return district.region

        polygons.sort(key=shift_borough)
        # polygons.sort(key=lambda x: x.index)

        return polygons

    @classmethod
    def load_districts(cls):
        cwd = os.path.dirname(__file__)
        return cls.load(os.path.join(cwd, cls.NYC_DISTRICTS_JSON))

    @classmethod
    def load_boroughs(cls):
        cwd = os.path.dirname(__file__)
        return cls.load(os.path.join(cwd, cls.NYC_BOROUGHS_JSON))
