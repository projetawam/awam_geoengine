# Data Cleaning & Validation Report (v2)
*Generated on: 2026-09-01 13:16:00*

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
| `AWAM_Earthdata_makthar_ALL_ECOSTRESS-LST_20250501_20260811_v2.parquet` | ECOSTRESS-LST | 2,479 | 2,423 | 56 | 0 | 0 | 0 | 56 | 97.7% |
| `AWAM_Earthdata_makthar_ALL_ECOSTRESS-LST_20260722_20260901_v2.parquet` | ECOSTRESS-LST | 98 | 98 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_Earthdata_makthar_ALL_ECOSTRESS-LST_20260730_20260901_v2.parquet` | ECOSTRESS-LST | 110 | 110 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_Earthdata_makthar_ALL_NISAR-Backscatter_20260617_20260811_v2.parquet` | NISAR-Backscatter | 4,370 | 2,972 | 1,398 | 0 | 0 | 1 | 1,397 | 68.0% |
| `AWAM_Earthdata_makthar_ALL_NISAR-Backscatter_20260617_20260901_v2.parquet` | NISAR-Backscatter | 7,341 | 4,545 | 2,796 | 0 | 0 | 1 | 2,795 | 61.9% |
| `AWAM_Earthdata_makthar_ALL_NISAR-SoilMoisture_20260617_20260811_v2.parquet` | NISAR-SoilMoisture | 60 | 60 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_Earthdata_makthar_ALL_NISAR-SoilMoisture_20260617_20260821_v2.parquet` | NISAR-SoilMoisture | 72 | 72 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_Earthdata_makthar_ALL_NISAR-SoilMoisture_20260617_20260901_v2.parquet` | NISAR-SoilMoisture | 90 | 90 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_Earthdata_sidi-mechreg_ALL_ECOSTRESS-LST_20250501_20260811_v2.parquet` | ECOSTRESS-LST | 1,678 | 1,678 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_Earthdata_sidi-mechreg_ALL_ECOSTRESS-LST_20260722_20260901_v2.parquet` | ECOSTRESS-LST | 153 | 153 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_Earthdata_sidi-mechreg_ALL_ECOSTRESS-LST_20260730_20260901_v2.parquet` | ECOSTRESS-LST | 153 | 153 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_Earthdata_sidi-mechreg_ALL_NISAR-Backscatter_20260617_20260811_v2.parquet` | NISAR-Backscatter | 4,770 | 3,801 | 969 | 0 | 0 | 0 | 969 | 79.7% |
| `AWAM_Earthdata_sidi-mechreg_ALL_NISAR-Backscatter_20260617_20260901_v2.parquet` | NISAR-Backscatter | 7,873 | 6,390 | 1,483 | 0 | 0 | 0 | 1,483 | 81.2% |
| `AWAM_Earthdata_sidi-mechreg_ALL_NISAR-SoilMoisture_20260617_20260811_v2.parquet` | NISAR-SoilMoisture | 78 | 40 | 38 | 15 | 0 | 0 | 23 | 51.3% |
| `AWAM_Earthdata_sidi-mechreg_ALL_NISAR-SoilMoisture_20260617_20260821_v2.parquet` | NISAR-SoilMoisture | 89 | 48 | 41 | 17 | 0 | 0 | 24 | 53.9% |
| `AWAM_Earthdata_sidi-mechreg_ALL_NISAR-SoilMoisture_20260617_20260901_v2.parquet` | NISAR-SoilMoisture | 109 | 60 | 49 | 21 | 0 | 0 | 28 | 55.0% |
| `AWAM_GEE_makthar_ALL_ERA5-Meteo_20250501_20260811_v2.parquet` | ERA5-Meteo | 2,760 | 2,760 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_GEE_makthar_ALL_ERA5-Meteo_20260730_20260901_v2.parquet` | ERA5-Meteo | 156 | 156 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_GEE_makthar_ALL_Landsat-Thermal_20250501_20260811_v2.parquet` | Landsat-Thermal | 6,168 | 6,163 | 5 | 0 | 0 | 0 | 5 | 99.9% |
| `AWAM_GEE_makthar_ALL_Landsat-Thermal_20260730_20260901_v2.parquet` | Landsat-Thermal | 539 | 539 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_GEE_makthar_ALL_MODIS-LST_20250501_20260811_v2.parquet` | MODIS-LST | 1,877 | 1,877 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_GEE_makthar_ALL_MODIS-LST_20260730_20260901_v2.parquet` | MODIS-LST | 186 | 186 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_GEE_makthar_ALL_S1-SAR_20250501_20260811_v2.parquet` | S1-SAR | 173,327 | 171,597 | 1,730 | 0 | 1,730 | 0 | 0 | 99.0% |
| `AWAM_GEE_makthar_ALL_S1-SAR_20260730_20260901_v2.parquet` | S1-SAR | 11,357 | 11,240 | 117 | 0 | 117 | 0 | 0 | 99.0% |
| `AWAM_GEE_makthar_ALL_S2-Indices_20250501_20260811_v2.parquet` | S2-Indices | 63,391 | 55,578 | 7,813 | 0 | 0 | 0 | 7,813 | 87.7% |
| `AWAM_GEE_makthar_ALL_S2-Indices_20260730_20260901_v2.parquet` | S2-Indices | 1,614 | 1,531 | 83 | 0 | 0 | 0 | 83 | 94.9% |
| `AWAM_GEE_sidi-mechreg_ALL_ERA5-Meteo_20250501_20260811_v2.parquet` | ERA5-Meteo | 2,300 | 2,300 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_GEE_sidi-mechreg_ALL_ERA5-Meteo_20260730_20260901_v2.parquet` | ERA5-Meteo | 130 | 130 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_GEE_sidi-mechreg_ALL_Landsat-Thermal_20250501_20260811_v2.parquet` | Landsat-Thermal | 1,512 | 1,512 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_GEE_sidi-mechreg_ALL_Landsat-Thermal_20260730_20260901_v2.parquet` | Landsat-Thermal | 165 | 165 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_GEE_sidi-mechreg_ALL_MODIS-LST_20250501_20260811_v2.parquet` | MODIS-LST | 1,585 | 1,585 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_GEE_sidi-mechreg_ALL_MODIS-LST_20260730_20260901_v2.parquet` | MODIS-LST | 141 | 141 | 0 | 0 | 0 | 0 | 0 | 100.0% |
| `AWAM_GEE_sidi-mechreg_ALL_S1-SAR_20250501_20260811_v2.parquet` | S1-SAR | 106,815 | 105,163 | 1,652 | 0 | 1,221 | 292 | 139 | 98.5% |
| `AWAM_GEE_sidi-mechreg_ALL_S1-SAR_20260730_20260901_v2.parquet` | S1-SAR | 8,135 | 8,050 | 85 | 0 | 85 | 0 | 0 | 99.0% |
| `AWAM_GEE_sidi-mechreg_ALL_S2-Indices_20250501_20260811_v2.parquet` | S2-Indices | 52,477 | 36,433 | 16,044 | 0 | 0 | 0 | 16,044 | 69.4% |
| `AWAM_GEE_sidi-mechreg_ALL_S2-Indices_20260730_20260901_v2.parquet` | S2-Indices | 5,612 | 3,595 | 2,017 | 0 | 0 | 0 | 2,017 | 64.1% |

### Overall Metrics

- **Total Raw Records Extracted:** 469,770
- **Total Clean Records Preserved:** 433,394
- **Total Records Filtered:** 36,376
- **Overall Data Retention Rate:** 92.26%

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
