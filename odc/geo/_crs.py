# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
import math
import warnings
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Tuple, Union

import cachetools
import numpy
from pyproj.crs import CRS as _CRS
from pyproj.enums import WktVersion
from pyproj.exceptions import CRSError
from pyproj.transformer import Transformer

SomeCRS = Union[str, "CRS", _CRS, Dict[str, Any]]
MaybeCRS = Optional[SomeCRS]


@cachetools.cached({})
def _make_crs(crs_str: str) -> Tuple[_CRS, Optional[int]]:
    crs = _CRS.from_user_input(crs_str)
    return (crs, crs.to_epsg())


def _make_crs_transform_key(from_crs, to_crs, always_xy):
    return (id(from_crs), id(to_crs), always_xy)


@cachetools.cached({}, key=_make_crs_transform_key)
def _make_crs_transform(from_crs, to_crs, always_xy):
    return Transformer.from_crs(from_crs, to_crs, always_xy=always_xy).transform


def _guess_crs_str(crs_spec: Any) -> Optional[str]:
    """
    Returns a string representation of the crs spec.
    Returns `None` if it does not understand the spec.
    """
    if isinstance(crs_spec, str):
        return crs_spec
    if isinstance(crs_spec, dict):
        crs_spec = _CRS.from_dict(crs_spec)

    if hasattr(crs_spec, "to_epsg"):
        epsg = crs_spec.to_epsg()
        if epsg is not None:
            return f"EPSG:{crs_spec.to_epsg()}"
    if hasattr(crs_spec, "to_wkt"):
        return crs_spec.to_wkt()
    return None


class CRS:
    """
    Wrapper around `pyproj.CRS` for backwards compatibility.
    """

    DEFAULT_WKT_VERSION = WktVersion.WKT2_2019
    __slots__ = ("_crs", "_epsg", "_str")

    def __init__(self, crs_str: Any):
        """
        :param crs_str: string representation of a CRS, often an EPSG code like 'EPSG:4326'
        :raises: `pyproj.exceptions.CRSError`
        """
        crs_str = _guess_crs_str(crs_str)
        if crs_str is None:
            raise CRSError(
                "Expect string or any object with `.to_epsg()` or `.to_wkt()` method"
            )

        _crs, _epsg = _make_crs(crs_str)

        self._crs = _crs
        self._epsg = _epsg
        self._str = crs_str

    def __getstate__(self):
        return {"crs_str": self._str}

    def __setstate__(self, state):
        self.__init__(state["crs_str"])

    def to_wkt(self, pretty: bool = False, version: Optional[WktVersion] = None) -> str:
        """
        WKT representation of the CRS
        """
        if version is None:
            version = self.DEFAULT_WKT_VERSION

        return self._crs.to_wkt(pretty=pretty, version=version)

    @property
    def wkt(self) -> str:
        return self.to_wkt(version=WktVersion.WKT1_GDAL)

    def to_epsg(self) -> Optional[int]:
        """
        EPSG Code of the CRS or None
        """
        return self._epsg

    @property
    def epsg(self) -> Optional[int]:
        return self._epsg

    @property
    def semi_major_axis(self):
        return self._crs.ellipsoid.semi_major_metre

    @property
    def semi_minor_axis(self):
        return self._crs.ellipsoid.semi_minor_metre

    @property
    def inverse_flattening(self):
        return self._crs.ellipsoid.inverse_flattening

    @property
    def geographic(self) -> bool:
        return self._crs.is_geographic

    @property
    def projected(self) -> bool:
        return self._crs.is_projected

    @property
    def dimensions(self) -> Tuple[str, str]:
        """
        List of dimension names of the CRS.
        The ordering of the names is intended to reflect the `numpy` array axis order of the loaded raster.
        """
        if self.geographic:
            return "latitude", "longitude"

        if self.projected:
            return "y", "x"

        raise ValueError("Neither projected nor geographic")  # pragma: no cover

    @property
    def units(self) -> Tuple[str, str]:
        """
        List of dimension units of the CRS.
        The ordering of the units is intended to reflect the `numpy` array axis order of the loaded raster.
        """
        if self.geographic:
            return "degrees_north", "degrees_east"

        if self.projected:
            x, y = self._crs.axis_info
            return x.unit_name, y.unit_name

        raise ValueError("Neither projected nor geographic")  # pragma: no cover

    def __str__(self) -> str:
        return self._str

    def __hash__(self) -> int:
        return hash(self.to_wkt())

    def __repr__(self) -> str:
        return f"CRS('{self._str}')"

    def __eq__(self, other) -> bool:
        if not isinstance(other, CRS):
            try:
                other = CRS(other)
            except Exception:  # pylint: disable=broad-except
                return False

        if self._crs is other._crs:
            return True

        if self.epsg is not None and other.epsg is not None:
            return self.epsg == other.epsg

        return self._crs == other._crs

    def __ne__(self, other) -> bool:
        return not self == other

    @property
    def proj(self) -> _CRS:
        """Access proj.CRS object that this wraps"""
        return self._crs

    @property
    def valid_region(self) -> Optional["_geom.Geometry"]:
        """Return valid region of this CRS.

        Bounding box in Lon/Lat as a 4 point Polygon in EPSG:4326.
        None if not defined
        """

        from . import _geom  # pylint: disable=import-outside-toplevel

        aou = self._crs.area_of_use
        if aou is None:
            return None
        return _geom.box(aou.west, aou.south, aou.east, aou.north, "EPSG:4326")

    @property
    def crs_str(self) -> str:
        """DEPRECATED"""
        warnings.warn(
            "Please use `str(crs)` instead of `crs.crs_str`",
            category=DeprecationWarning,
        )
        return self._str

    def transformer_to_crs(
        self, other: "CRS", always_xy=True
    ) -> Callable[[Any, Any], Tuple[Any, Any]]:
        """
        Returns a function that maps x, y -> x', y' where x, y are coordinates in
        this stored either as scalars or ndarray objects and x', y' are the same
        points in the `other` CRS.
        """

        # pylint: disable=protected-access
        transform = _make_crs_transform(self._crs, other._crs, always_xy=always_xy)

        def result(x, y):
            rx, ry = transform(x, y)  # pylint: disable=unpacking-non-sequence

            if not isinstance(rx, numpy.ndarray) or not isinstance(ry, numpy.ndarray):
                return (rx, ry)

            missing = numpy.isnan(rx) | numpy.isnan(ry)
            rx[missing] = numpy.nan
            ry[missing] = numpy.nan
            return (rx, ry)

        return result


class CRSMismatchError(ValueError):
    """
    Raised when geometry operation is attempted on geometries in different
    coordinate references.
    """


def norm_crs(crs: MaybeCRS) -> Optional[CRS]:
    """Normalise CRS representation."""
    if isinstance(crs, CRS):
        return crs
    if crs is None:
        return None
    return CRS(crs)


def norm_crs_or_error(crs: MaybeCRS) -> CRS:
    """Normalise CRS representation, raise error if input is ``None``."""
    if isinstance(crs, CRS):
        return crs
    if crs is None:
        raise ValueError("Expect valid CRS")
    return CRS(crs)


def crs_units_per_degree(
    crs: SomeCRS,
    lon: Union[float, Tuple[float, float]],
    lat: float = 0,
    step: float = 0.1,
) -> float:
    """Compute number of CRS units per degree for a projected CRS at a given location
    in lon/lat.

    Location can be supplied as a tuple or as two arguments.

    Returns
    -------
    A floating number S such that `S*degrees -> meters`
    """

    from . import _geom  # pylint: disable=import-outside-toplevel

    if isinstance(lon, tuple):
        lon, lat = lon

    lon2 = lon + step
    if lon2 > 180:
        lon2 = lon - step

    ll = _geom.line([(lon, lat), (lon2, lat)], "EPSG:4326")
    xy = ll.to_crs(crs, resolution=math.inf)

    return xy.length / step


if TYPE_CHECKING:
    from . import _geom  # pragma: no cover