# coding=utf-8
import os
from textwrap import dedent

import pytest

from datacube.model import _uri_to_local_path, Dataset, DatasetMatcher, StorageType, GeoPolygon, GeoBox


def test_uri_to_local_path():
    if os.name == 'nt':
        assert 'C:\\tmp\\test.tmp' == str(_uri_to_local_path('file:///C:/tmp/test.tmp'))

    else:
        assert '/tmp/something.txt' == str(_uri_to_local_path('file:///tmp/something.txt'))

    assert _uri_to_local_path(None) is None

    with pytest.raises(ValueError):
        _uri_to_local_path('ftp://example.com/tmp/something.txt')


def test_doctest_local_path():
    if os.name == 'nt':
        dataset = Dataset(None, None, 'file:///C:/tmp/test.tmp')

        assert str(dataset.local_path) == 'C:\\tmp\\test.tmp'

    else:
        dataset = Dataset(None, None, 'file:///tmp/something.txt')

        assert str(dataset.local_path) == '/tmp/something.txt'

    dataset = Dataset(None, None, None).local_path is None

    with pytest.raises(ValueError):
        Dataset(None, None, 'ftp://example.com/tmp/something.txt').local_path


def test_dataset_matcher_repr():
    ds_matcher = DatasetMatcher(metadata={'flim': 'flam'})

    rep = repr(ds_matcher)
    assert 'flim' in rep
    assert 'flam' in rep


SAMPLE_STORAGE_TYPE = {
    'description': 'LS5 NBAR 25 metre, 100km tile, Albers projection',
    'file_path_template': '{platform[code]}_{instrument[name]}_NBAR_3577_'
                          '{tile_index[0]}_{tile_index[1]}_{start_time}.nc',
    'global_attributes': {
        'license': 'Creative Commons Attribution 4.0 International CC BY 4.0',
        'product_version': '0.0.0',
        'source': 'This data is a reprojection and retile of Landsat surface '
                  'reflectance scene data available from /g/data/rs0/scenes/',
        'summary': 'These files are experimental, short lived, and the format will change.',
        'title': 'Experimental Data files From the Australian Geoscience Data Cube - DO NOT USE'},
    'location_name': 'eotiles',
    'match': {
        'metadata': {
            'instrument': {'name': 'TM'},
            'platform': {'code': 'LANDSAT_5'},
            'product_type': 'NBAR'}},
    'measurements': {
        '10': {
            'attrs': {
                'long_name': 'Nadir BRDF Adjusted Reflectance 0.45-0.52 microns',
                'standard_name': 'surface_bidirectional_reflectance'},
            'dtype': 'int16',
            'nodata': -999,
            'resampling_method': 'nearest',
            'varname': 'band_10',
            'zlib': True},
        '20': {
            'attrs': {
                'long_name': 'Nadir BRDF Adjusted Reflectance 0.52-0.60 microns',
                'standard_name': 'surface_bidirectional_reflectance'},
            'dtype': 'int16',
            'nodata': -999,
            'resampling_method': 'nearest',
            'varname': 'band_20',
            'zlib': True}},
    'name': 'ls5_nbar_albers',
    'storage': {
        'chunking': {'time': 1, 'x': 500, 'y': 500},
        'crs': dedent("""\
            PROJCS["GDA94 / Australian Albers",
                GEOGCS["GDA94",
                    DATUM["Geocentric_Datum_of_Australia_1994",
                        SPHEROID["GRS 1980",6378137,298.257222101,
                            AUTHORITY["EPSG","7019"]],
                        TOWGS84[0,0,0,0,0,0,0],
                        AUTHORITY["EPSG","6283"]],
                    PRIMEM["Greenwich",0,
                        AUTHORITY["EPSG","8901"]],
                    UNIT["degree",0.01745329251994328,
                        AUTHORITY["EPSG","9122"]],
                    AUTHORITY["EPSG","4283"]],
                UNIT["metre",1,
                    AUTHORITY["EPSG","9001"]],
                PROJECTION["Albers_Conic_Equal_Area"],
                PARAMETER["standard_parallel_1",-18],
                PARAMETER["standard_parallel_2",-36],
                PARAMETER["latitude_of_center",0],
                PARAMETER["longitude_of_center",132],
                PARAMETER["false_easting",0],
                PARAMETER["false_northing",0],
                AUTHORITY["EPSG","3577"],
                AXIS["Easting",EAST],
                AXIS["Northing",NORTH]]
            """),
        'dimension_order': ['time', 'y', 'x'],
        'driver': 'NetCDF CF',
        'resolution': {'x': 25, 'y': -25},
        'tile_size': {'x': 100000.0, 'y': 100000.0}}}


def test_storage_type_model():
    st = StorageType(SAMPLE_STORAGE_TYPE, target_dataset_type_id=None)


def test_geobox():
    points_list = [
        [(148.2697, -35.20111), (149.31254, -35.20111), (149.31254, -36.331431), (148.2697, -36.331431)],
        [(148.2697, 35.20111), (149.31254, 35.20111), (149.31254, 36.331431), (148.2697, 36.331431)],
        [(-148.2697, 35.20111), (-149.31254, 35.20111), (-149.31254, 36.331431), (-148.2697, 36.331431)],
        [(-148.2697, -35.20111), (-149.31254, -35.20111), (-149.31254, -36.331431), (-148.2697, -36.331431)],
        ]
    for points in points_list:
        polygon = GeoPolygon(points, 'EPSG:3577')
        resolution = (25, -25)
        geobox = GeoBox.from_geopolygon(polygon, resolution)

        assert abs(resolution[0]) > abs(geobox.extent.boundingbox.left - polygon.boundingbox.left)
        assert abs(resolution[0]) > abs(geobox.extent.boundingbox.right - polygon.boundingbox.right)
        assert abs(resolution[1]) > abs(geobox.extent.boundingbox.top - polygon.boundingbox.top)
        assert abs(resolution[1]) > abs(geobox.extent.boundingbox.bottom - polygon.boundingbox.bottom)
