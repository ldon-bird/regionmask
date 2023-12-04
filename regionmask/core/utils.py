import warnings

import numpy as np
import shapely
import xarray as xr
from packaging.version import Version


def _total_bounds(polygons):

    if Version(shapely.__version__) > Version("2.0b1"):

        return shapely.total_bounds(polygons)

    bounds = np.array([p.bounds for p in polygons])

    xmin = bounds[:, 0].min()
    ymin = bounds[:, 1].min()
    xmax = bounds[:, 2].max()
    ymax = bounds[:, 3].max()

    return [xmin, ymin, xmax, ymax]


def _flatten_polygons(polygons, error="raise"):

    from shapely.geometry import MultiPolygon, Polygon

    if error not in ["raise", "skip"]:
        raise ValueError("'error' must be one of 'raise' and 'skip'")

    polys = []
    for p in polygons:
        if isinstance(p, MultiPolygon):
            polys += list(p.geoms)
        elif isinstance(p, Polygon):
            polys += [p]
        else:
            if error == "raise":
                msg = f"Expected 'Polygon' or 'MultiPolygon', found {type(p)}"
                raise TypeError(msg)

    return polys


def _maybe_to_dict(keys, values):
    """convert iterable to dict if necessary"""

    if not isinstance(values, dict):
        values = {key: value for key, value in zip(keys, values)}

    return values


def _create_dict_of_numbered_string(numbers, string):

    return {number: string + str(number) for number in numbers}


def _sanitize_names_abbrevs(numbers, values, default):

    if isinstance(values, str):
        values = _create_dict_of_numbered_string(numbers, values)
    elif values is None:
        values = _create_dict_of_numbered_string(numbers, default)
    else:
        if not len(numbers) == len(values):
            raise ValueError("`numbers` and `values` do not have the same length.")

        values = _maybe_to_dict(numbers, values)

    return values


def _wrapAngle360(lon):
    """wrap angle to `[0, 360[`."""
    lon = np.array(lon)
    return np.mod(lon, 360)


def _wrapAngle180(lon):
    """wrap angle to `[-180, 180[`."""
    lon = np.array(lon)
    sel = (lon < -180) | (180 <= lon)
    lon[sel] = _wrapAngle360(lon[sel] + 180) - 180
    return lon


def _wrapAngle(lon, wrap_lon=True, is_unstructured=False):
    """wrap the angle to the other base

    If lon is from -180 to 180 wraps them to 0..360
    If lon is from 0 to 360 wraps them to -180..180
    """

    if np.isscalar(lon):
        lon = [lon]

    lon = np.array(lon)

    if wrap_lon is True:
        mn, mx = np.nanmin(lon), np.nanmax(lon)
        msg = "Cannot infer the transformation."
        wrap_lon = 360 if _is_180(mn, mx, msg_add=msg) else 180

    if wrap_lon == 180:
        lon = _wrapAngle180(lon)

    if wrap_lon == 360:
        lon = _wrapAngle360(lon)

    # check if they are still unique
    if lon.ndim == 1 and not is_unstructured:
        if lon.shape != np.unique(lon).shape:
            raise ValueError("There are equal longitude coordinates (when wrapped)!")

    return lon


def _is_180(lon_min, lon_max, msg_add=""):

    lon_min = np.round(lon_min, 6)
    lon_max = np.round(lon_max, 6)

    if (lon_min < 0) and (lon_max > 180):
        msg = f"lon has data that is larger than 180 and smaller than 0. {msg_add}"
        raise ValueError(msg)

    return lon_max <= 180


def create_lon_lat_dataarray_from_bounds(
    lon_start, lon_stop, lon_step, lat_start, lat_stop, lat_step
):
    """example xarray Dataset

    Parameters
    ----------
    lon_start : number
        Start of lon bounds. The bounds includes this value.
    lon_stop : number
        End of lon bounds. The bounds does not include this value.
    lon_step : number
        Spacing between values.
    lat_start : number
        Start of lat bounds. The bounds includes this value.
    lat_stop : number
        End of lat bounds. The bounds does not include this value.
    lat_step : number
        Spacing between values.

    Returns
    -------
    ds : xarray Dataarray
        Example dataset including, lon, lat, lon_bnds, lat_bnds.

    """

    lon_bnds = np.arange(lon_start, lon_stop, lon_step)
    lon = (lon_bnds[:-1] + lon_bnds[1:]) / 2

    lat_bnds = np.arange(lat_start, lat_stop, lat_step)
    lat = (lat_bnds[:-1] + lat_bnds[1:]) / 2

    LON, LAT = np.meshgrid(lon, lat)

    ds = xr.Dataset(
        coords=dict(
            lon=lon,
            lat=lat,
            lon_bnds=lon_bnds,
            lat_bnds=lat_bnds,
            LON=(("lat", "lon"), LON),
            LAT=(("lat", "lon"), LAT),
        )
    )

    return ds


def _is_numeric(numbers):

    numbers = np.asarray(numbers)
    return np.issubdtype(numbers.dtype, np.number)


def equally_spaced(*args):

    args = [np.asarray(arg) for arg in args]

    if any(arg.ndim > 1 for arg in args):
        return False

    if any(arg.size < 2 for arg in args):
        return False

    d_args = (np.diff(arg) for arg in args)

    return all(np.allclose(d_arg[0], d_arg) for d_arg in d_args)


def _equally_spaced_on_split_lon(lon):

    lon = np.asarray(lon)

    if lon.ndim > 1 or lon.size < 2:
        return False

    d_lon = np.diff(lon)
    d_lon_not_isclose = ~np.isclose(d_lon[0], d_lon)

    # there can only be one breakpoint
    return (d_lon_not_isclose.sum() == 1) and not d_lon_not_isclose[-1]


def _find_splitpoint(lon):

    lon = np.asarray(lon)
    d_lon = np.diff(lon)

    d_lon_not_isclose = ~np.isclose(d_lon[0], d_lon)

    split_point = np.argwhere(d_lon_not_isclose)

    if len(split_point) != 1:
        raise ValueError("more or less than one split point found")

    return split_point.squeeze() + 1


def _sample_coords(coord):
    """Sample coords for percentage overlap."""

    n = 10

    coord = np.asarray(coord)

    d_coord = coord[1] - coord[0]

    n_cells = coord.size

    left = coord[0] - d_coord / 2 + d_coord / (n * 2)
    right = coord[-1] + d_coord / 2 - d_coord / (n * 2)

    return np.linspace(left, right, n_cells * n)


def unpackbits(numbers, num_bits):
    "Unpacks elements of a array into a binary-valued output array."

    # after https://stackoverflow.com/a/51509307/3010700

    if np.issubdtype(numbers.dtype, np.floating):
        raise ValueError("numpy data type needs to be int-like")
    shape = numbers.shape + (num_bits,)

    numbers = numbers.reshape([-1, 1])
    mask = 2 ** np.arange(num_bits, dtype=numbers.dtype).reshape([1, num_bits])

    # avoid casting to float64
    out = np.empty(numbers.shape[0:1] + (num_bits,), dtype=bool)
    return np.bitwise_and(numbers, mask, out=out, casting="unsafe").reshape(shape)


def flatten_3D_mask(mask_3D):
    """flatten 3D masks

    Parameters
    ----------
    mask_3D : xr.DataArray
        3D mask to flatten and plot. Should be the result of
        `Regions.mask_3D(...)`.
    **kwargs : keyword arguments
        Keyword arguments passed to xr.plot.pcolormesh.

    Returns
    -------
    mesh : ``matplotlib.collections.QuadMesh``

    """

    if not isinstance(mask_3D, xr.DataArray):
        raise ValueError("expected a xarray.DataArray")

    if not mask_3D.ndim == 3:
        raise ValueError(f"``mask_3D`` must have 3 dimensions, found {mask_3D.ndim}")

    if "region" not in mask_3D.coords:
        raise ValueError("``mask_3D`` must contain the dimension 'region'")

    if (mask_3D.sum("region") > 1).any():
        warnings.warn(
            "Found overlapping regions which cannot correctly be reduced to a 2D mask",
            RuntimeWarning,
        )

    # flatten the mask
    mask_2D = (mask_3D * mask_3D.region).sum("region")

    # mask all gridpoints not belonging to any region
    return mask_2D.where(mask_3D.any("region"))


def _snap_polygon(polygon, to, atol, xy_col):
    """

    idx: x or y coordinate
    - 0: x-coord
    - 1: y-coord

    """

    arr = shapely.get_coordinates(polygon)

    sel = np.isclose(arr[:, xy_col], to, atol=atol)
    arr[sel, xy_col] = to

    return shapely.set_coordinates(polygon, arr)


def _snap_polygon_shapely_18(polygon, to, atol, xy_col):

    import shapely.ops

    def _snap_x(x, y, z=None):

        x = np.array(x)
        sel = np.isclose(x, to, atol=atol)
        x[sel] = to
        x = x.tolist()
        return tuple(filter(None, [x, y, z]))

    def _snap_y(x, y, z=None):

        y = np.array(y)
        sel = np.isclose(y, to, atol=atol)

        y[sel] = to
        y = y.tolist()
        return tuple(filter(None, [x, y, z]))

    _snap_func = _snap_x if xy_col == 0 else _snap_y

    polygon = shapely.ops.transform(_snap_func, polygon)

    return polygon


def _snap(df, idx, to, atol, xy_col):

    polygons = df.loc[idx].geometry.tolist()

    if Version(shapely.__version__) > Version("2.0.0"):
        polygons = [_snap_polygon(poly, to, atol, xy_col) for poly in polygons]
        df.loc[idx, "geometry"] = polygons

        return df

    polygons = [_snap_polygon_shapely_18(poly, to, atol, xy_col) for poly in polygons]

    for i, polygon in zip(idx, polygons):
        df.at[i, "geometry"] = polygon

    return df


def _snap_to_90S(df, idx, atol):

    return _snap(df, idx, to=-90, atol=atol, xy_col=1)


def _snap_to_180E(df, idx, atol):

    return _snap(df, idx, to=180, atol=atol, xy_col=0)
