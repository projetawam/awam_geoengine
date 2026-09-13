# Data Cleaning & Validation Report (v2)
*Generated on: 2026-09-13 13:27:57*

## Summary

This report documents the filtering, quality control, outlier removal, and deduplication
applied to the raw GeoParquet files extracted from GEE and NASA Earthdata.

"Merged (conflict)" rows are NOT lost data: they are rows that shared the same
(parcel_id, date, coords) key but disagreed on their measured values (e.g. two
genuine overlapping acquisitions on the same day). Their numeric columns were
averaged into a single row rather than one of them being silently discarded.

### Processing Results by File

| Filename | Datatype | Raw Rows | Clean Rows | Dropped | QC Drop | Outlier Drop | Dedup Drop | Merged (conflict) | Retained |
|----------|----------|---------:|-----------:|--------:|--------:|-------------:|-----------:|------------------:|---------:|
| `AWAM_Earthdata_makthar_ALL_ECOSTRESS-LST_20250501_20260811_v2.parquet, AWAM_Earthdata_makthar_ALL_ECOSTRESS-LST_20260722_20260901_v2.parquet, AWAM_Earthdata_makthar_ALL_ECOSTRESS-LST_20260730_20260901_v2.parquet` | ECOSTRESS-LST | 2,687 | 2,533 | 154 | 0 | 0 | 98 | 56 | 94.3% |
| `AWAM_Earthdata_makthar_ALL_NISAR-Backscatter_20260617_20260811_v2.parquet, AWAM_Earthdata_makthar_ALL_NISAR-Backscatter_20260617_20260901_v2.parquet` | NISAR-Backscatter | 11,711 | 4,545 | 7,166 | 0 | 0 | 4,371 | 2,795 | 38.8% |
| `AWAM_Earthdata_makthar_ALL_NISAR-SoilMoisture_20260617_20260811_v2.parquet, AWAM_Earthdata_makthar_ALL_NISAR-SoilMoisture_20260617_20260821_v2.parquet, AWAM_Earthdata_makthar_ALL_NISAR-SoilMoisture_20260617_20260901_v2.parquet` | NISAR-SoilMoisture | 222 | 90 | 132 | 0 | 0 | 132 | 0 | 40.5% |
| `AWAM_Earthdata_sidi-mechreg_ALL_ECOSTRESS-LST_20250501_20260811_v2.parquet, AWAM_Earthdata_sidi-mechreg_ALL_ECOSTRESS-LST_20260722_20260901_v2.parquet, AWAM_Earthdata_sidi-mechreg_ALL_ECOSTRESS-LST_20260730_20260901_v2.parquet` | ECOSTRESS-LST | 1,984 | 1,882 | 102 | 0 | 0 | 102 | 0 | 94.9% |
| `AWAM_Earthdata_sidi-mechreg_ALL_NISAR-Backscatter_20260617_20260811_v2.parquet, AWAM_Earthdata_sidi-mechreg_ALL_NISAR-Backscatter_20260617_20260901_v2.parquet` | NISAR-Backscatter | 12,643 | 6,502 | 6,141 | 0 | 0 | 4,624 | 1,517 | 51.4% |
| `AWAM_Earthdata_sidi-mechreg_ALL_NISAR-SoilMoisture_20260617_20260811_v2.parquet, AWAM_Earthdata_sidi-mechreg_ALL_NISAR-SoilMoisture_20260617_20260821_v2.parquet, AWAM_Earthdata_sidi-mechreg_ALL_NISAR-SoilMoisture_20260617_20260901_v2.parquet` | NISAR-SoilMoisture | 276 | 60 | 216 | 53 | 0 | 134 | 29 | 21.7% |
| `AWAM_GEE_makthar_ALL_ERA5-Meteo_20250501_20260811_v2.parquet, AWAM_GEE_makthar_ALL_ERA5-Meteo_20260730_20260901_v2.parquet` | ERA5-Meteo | 2,916 | 2,886 | 30 | 0 | 0 | 0 | 30 | 99.0% |
| `AWAM_GEE_makthar_ALL_Landsat-Thermal_20250501_20260811_v2.parquet, AWAM_GEE_makthar_ALL_Landsat-Thermal_20260730_20260901_v2.parquet` | Landsat-Thermal | 6,707 | 6,625 | 82 | 0 | 0 | 77 | 5 | 98.8% |
| `AWAM_GEE_makthar_ALL_MODIS-LST_20250501_20260811_v2.parquet, AWAM_GEE_makthar_ALL_MODIS-LST_20260730_20260901_v2.parquet` | MODIS-LST | 2,063 | 2,053 | 10 | 0 | 0 | 0 | 10 | 99.5% |
| `AWAM_GEE_makthar_ALL_S1-SAR_20250501_20260811_v2.parquet, AWAM_GEE_makthar_ALL_S1-SAR_20260730_20260901_v2.parquet` | S1-SAR | 184,684 | 178,601 | 6,083 | 0 | 1,845 | 4,238 | 0 | 96.7% |
| `AWAM_GEE_makthar_ALL_S2-Indices_20250501_20260811_v2.parquet, AWAM_GEE_makthar_ALL_S2-Indices_20260730_20260901_v2.parquet` | S2-Indices | 65,005 | 56,812 | 8,193 | 0 | 0 | 293 | 7,900 | 87.4% |
| `AWAM_GEE_sidi-mechreg_ALL_ERA5-Meteo_20250501_20260811_v2.parquet, AWAM_GEE_sidi-mechreg_ALL_ERA5-Meteo_20260730_20260901_v2.parquet` | ERA5-Meteo | 2,430 | 2,405 | 25 | 0 | 0 | 0 | 25 | 99.0% |
| `AWAM_GEE_sidi-mechreg_ALL_Landsat-Thermal_20250501_20260811_v2.parquet, AWAM_GEE_sidi-mechreg_ALL_Landsat-Thermal_20260730_20260901_v2.parquet` | Landsat-Thermal | 1,677 | 1,635 | 42 | 0 | 0 | 42 | 0 | 97.5% |
| `AWAM_GEE_sidi-mechreg_ALL_MODIS-LST_20250501_20260811_v2.parquet, AWAM_GEE_sidi-mechreg_ALL_MODIS-LST_20260730_20260901_v2.parquet` | MODIS-LST | 1,726 | 1,724 | 2 | 0 | 0 | 0 | 2 | 99.9% |
| `AWAM_GEE_sidi-mechreg_ALL_S1-SAR_20250501_20260811_v2.parquet, AWAM_GEE_sidi-mechreg_ALL_S1-SAR_20260730_20260901_v2.parquet` | S1-SAR | 114,950 | 110,744 | 4,206 | 0 | 1,295 | 2,472 | 439 | 96.3% |
| `AWAM_GEE_sidi-mechreg_ALL_S2-Indices_20250501_20260811_v2.parquet, AWAM_GEE_sidi-mechreg_ALL_S2-Indices_20260730_20260901_v2.parquet` | S2-Indices | 58,089 | 39,147 | 18,942 | 0 | 0 | 1,364 | 17,578 | 67.4% |

### Overall Metrics

- **Total Raw Records Extracted:** 469,770
- **Total Clean Records Preserved:** 418,244
- **Total Records Filtered:** 51,526
- **Overall Data Retention Rate:** 89.03%

---

## Applied Cleaning Rules Summary

1. **Sentinel-2 Indices (`S2-Indices`)**
   - Bound ratio indices (NDVI, SAVI, EVI, NDRE, NDWI, NDMI, BSI, NDSI) to `[-1.0, +1.0]`.
   - Bound `fCover` to `[0.0, +1.0]`.
   - Reject cloud leakage outliers where NDVI < -0.5.
   - Drop fully empty pixel observations (> 80% NaN).
   - Non-destructive dedup on `(parcel_id, date, longitude, latitude)`.

2. **Sentinel-1 SAR (`S1-SAR`)**
   - Clip backscatter VV_dB `[-30, +5]`, VH_dB `[-35, 0]`.
   - Speckle filter using IQR thresholding (1.5 x IQR) per parcel & date.
   - Non-destructive dedup on `(parcel_id, date, longitude, latitude)`.

3. **MODIS & Landsat & ECOSTRESS Thermal (`MODIS-LST`, `Landsat-Thermal`, `ECOSTRESS-LST`)**
   - Filter physical land surface temperature bounds `[250 K, 340 K]`.
   - ECOSTRESS: filter on the Mandatory QA bits (1:0) of the QC bitmask, masked with `& 0b11`
     (NOT the raw QC value).
   - ECOSTRESS: filter the dedicated cloud band (`cloud_flag == 0`), since the QC layer does
     not encode cloud information in product v002.
   - Non-destructive dedup on `(parcel_id, date, coords)`.

4. **AgERA5 / ERA5-Land Weather (`ERA5-Meteo`)**
   - Validate physical temperatures: Tmin in `[-15, 50] °C`, Tmax in `[-10, 55] °C`.
   - Assert logical consistency: `Tmin <= Tmax`.
   - Precipitation: clip GRIB-packing negative artifacts to 0; flag/drop values
     above 300 mm/day as likely packing artifacts.
   - Recalculate frost risk binary flag from validated Tmin.
   - Non-destructive dedup on `(parcel_id, date)`.

5. **NISAR Radar Products (`NISAR-SoilMoisture`, `NISAR-Backscatter`)**
   - Validate volumetric soil moisture bounds `[0.01, 0.60] m³/m³`.
   - Filter recommended quality flags (`QC == 0`).
   - Bound backscatter gamma0 powers and radar vegetation index (RVI).
   - Non-destructive dedup on `(parcel_id, date, longitude, latitude)`.
