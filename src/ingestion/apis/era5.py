"""ERA5 wave reanalysis data retrieval via Copernicus CDS API.

Setup:
    1. Register at https://cds.climate.copernicus.eu/
    2. Accept license for "ERA5 hourly data on single levels"
    3. Create ~/.cdsapirc with your UID and API key:
       url: https://cds.climate.copernicus.eu/api
       key: <your-key>
"""

import cdsapi
import json
import logging
import numpy as np
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ERA5 wave parameters available on single levels
ERA5_WAVE_VARS = [
    "significant_height_of_combined_wind_waves_and_swell",  # wave_height_m
    "mean_wave_period",                                       # wave_period_s
    "mean_wave_direction",                                    # wave_direction_deg
    "peak_wave_period",                                       # swell_period_s (peak)
    "mean_direction_of_wind_waves",
    "mean_direction_of_total_swell",
    "significant_height_of_wind_waves",
    "significant_height_of_total_swell",
    "mean_period_of_total_swell",
    # Wind (10m)
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
]

# Japan bounding box: 20°N-50°N, 120°E-155°E
JAPAN_AREA = [50, 120, 20, 155]  # north, west, south, east


def fetch_era5_month(year: int, month: int, output_path: Path) -> Path:
    """Download one month of ERA5 wave data for Japan as NetCDF.

    Args:
        year: e.g. 1990
        month: 1-12
        output_path: Directory to save the file

    Returns:
        Path to the downloaded .nc file
    """
    client = cdsapi.Client()
    output_path.mkdir(parents=True, exist_ok=True)
    nc_file = output_path / f"era5_waves_{year}_{month:02d}.nc"

    if nc_file.exists():
        logger.info(f"Already exists, skipping: {nc_file}")
        return nc_file

    logger.info(f"Downloading ERA5: {year}-{month:02d}")
    client.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable": ERA5_WAVE_VARS,
            "year": str(year),
            "month": f"{month:02d}",
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": JAPAN_AREA,
            "format": "netcdf",
        },
        str(nc_file),
    )
    logger.info(f"Downloaded: {nc_file}")
    return nc_file


def _unzip_era5(nc_file: Path) -> tuple[Path, Path]:
    """Unzip ERA5 download (CDS returns a ZIP with two NetCDF files).

    Returns:
        (wave_nc_path, oper_nc_path)
    """
    import zipfile
    cache_dir = nc_file.parent
    wave_nc = cache_dir / (nc_file.stem + "_wave.nc")
    oper_nc = cache_dir / (nc_file.stem + "_oper.nc")

    if wave_nc.exists() and oper_nc.exists():
        return wave_nc, oper_nc

    with zipfile.ZipFile(nc_file) as zf:
        names = zf.namelist()
        for name in names:
            extracted = cache_dir / name
            if not extracted.exists():
                zf.extract(name, cache_dir)
            # Identify wave vs oper file by variable contents
            import netCDF4 as nc4
            ds = nc4.Dataset(extracted)
            variables = list(ds.variables.keys())
            ds.close()
            if "swh" in variables:
                extracted.rename(wave_nc)
            elif "u10" in variables:
                extracted.rename(oper_nc)

    return wave_nc, oper_nc


def extract_spot_timeseries(nc_file: Path, lat: float, lon: float) -> list[dict]:
    """Extract hourly time series for a specific lat/lon from ERA5 download.

    ERA5 CDS API returns a ZIP containing two NetCDF files:
    - wave file (swh, mwp, mwd, shts, mpts, mdts, ...)
    - oper file (u10, v10 wind components)

    Args:
        nc_file: Path to ERA5 .nc file (may be a ZIP)
        lat: Spot latitude
        lon: Spot longitude

    Returns:
        List of dicts with hourly conditions
    """
    try:
        import netCDF4 as nc4
    except ImportError:
        raise ImportError("pip install netCDF4 to read ERA5 NetCDF files")

    import zipfile
    if zipfile.is_zipfile(nc_file):
        wave_nc, oper_nc = _unzip_era5(nc_file)
    else:
        # Single NetCDF file (e.g. already extracted)
        wave_nc = nc_file
        oper_nc = None

    def _get_nearest_idx(ds, lat, lon):
        lats = ds.variables["latitude"][:]
        lons = ds.variables["longitude"][:]
        lon_norm = lon % 360
        lat_idx = int(np.argmin(np.abs(lats - lat)))
        lon_idx = int(np.argmin(np.abs(lons - lon_norm)))

        # Check if this point is masked (land) in the first timestep; if so,
        # find the nearest valid ocean grid point within a 5-cell radius.
        first_var = [v for v in ds.variables if v not in ("latitude", "longitude", "valid_time", "number", "expver")]
        if first_var:
            sample = ds.variables[first_var[0]][0, lat_idx, lon_idx]
            if hasattr(sample, "mask") and np.ma.is_masked(sample):
                best_idx, best_dist = (lat_idx, lon_idx), 999.0
                for di in range(-5, 6):
                    for dj in range(-5, 6):
                        ni, nj = lat_idx + di, lon_idx + dj
                        if 0 <= ni < len(lats) and 0 <= nj < len(lons):
                            v = ds.variables[first_var[0]][0, ni, nj]
                            if not (hasattr(v, "mask") and np.ma.is_masked(v)):
                                dist = (di**2 + dj**2) ** 0.5
                                if dist < best_dist:
                                    best_dist = dist
                                    best_idx = (ni, nj)
                lat_idx, lon_idx = best_idx

        return lat_idx, lon_idx

    def _get_times(ds):
        times = ds.variables["valid_time"]
        return nc4.num2date(times[:], times.units)

    def _get_var(ds, name, t, lat_idx, lon_idx):
        if name not in ds.variables:
            return None
        v = ds.variables[name][t, lat_idx, lon_idx]
        if hasattr(v, "mask") and np.ma.is_masked(v):
            return None
        return float(v)

    # --- Wave file ---
    ds_wave = nc4.Dataset(wave_nc)
    lat_idx_w, lon_idx_w = _get_nearest_idx(ds_wave, lat, lon)
    time_vals = _get_times(ds_wave)

    # --- Oper file (wind) ---
    ds_oper = nc4.Dataset(oper_nc) if oper_nc and oper_nc.exists() else None
    if ds_oper:
        lat_idx_o, lon_idx_o = _get_nearest_idx(ds_oper, lat, lon)

    records = []
    try:
        for t_idx, t in enumerate(time_vals):
            timestamp = datetime(t.year, t.month, t.day, t.hour)

            # Wind
            wind_speed = wind_dir = None
            if ds_oper:
                u10 = _get_var(ds_oper, "u10", t_idx, lat_idx_o, lon_idx_o)
                v10 = _get_var(ds_oper, "v10", t_idx, lat_idx_o, lon_idx_o)
                if u10 is not None and v10 is not None:
                    wind_speed = float(np.sqrt(u10**2 + v10**2))
                    wind_dir = float(np.degrees(np.arctan2(u10, v10)) % 360)

            records.append({
                "timestamp": timestamp.isoformat(),
                "wave_height_m":       _get_var(ds_wave, "swh",  t_idx, lat_idx_w, lon_idx_w),
                "wave_period_s":       _get_var(ds_wave, "mwp",  t_idx, lat_idx_w, lon_idx_w),
                "wave_direction_deg":  _get_var(ds_wave, "mwd",  t_idx, lat_idx_w, lon_idx_w),
                "swell_height_m":      _get_var(ds_wave, "shts", t_idx, lat_idx_w, lon_idx_w),
                "swell_period_s":      _get_var(ds_wave, "mpts", t_idx, lat_idx_w, lon_idx_w),
                "swell_direction_deg": _get_var(ds_wave, "mdts", t_idx, lat_idx_w, lon_idx_w),
                "wind_speed_ms":       wind_speed,
                "wind_direction_deg":  wind_dir,
                "data_source": "era5",
                "is_forecast": 0,
            })
    finally:
        ds_wave.close()
        if ds_oper:
            ds_oper.close()

    return records


def load_spots(spots_json: Path) -> list[dict]:
    with open(spots_json) as f:
        return json.load(f)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Quick test: fetch one month
    out = Path("data/era5_cache")
    nc = fetch_era5_month(2020, 1, out)
    print(f"Downloaded: {nc}")
