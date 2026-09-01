# AWAM GeoEngine & Analytical Pipeline

> **Wallah We Can (WWC) GeoAI Agronomic Analytics Platform**  
> Multi-sensor satellite extraction, VARI calibration, plant health diagnostics, smart irrigation detection, and agronomic risk alert engines.

---

## 📁 Repository Architecture

```text
AWAM_GEOENGINE/
├── EXTRACT/             # Multi-sensor extraction (GEE, NASA Earthdata, NISAR, ERA5) & cleaning
├── VARI_CALIBRATION/    # Ground DNG image processing & Sentinel-2 sub-pixel unmixing calibration
├── PIPELINE_MASTER/     # Master orchestrator, global config, unified logging, and schema validator
├── SANTE_PLANTES/       # Composite plant health scoring, LAI Beer-Lambert, AWAM index & status
├── IRRIGATION/          # Water deficit estimation, irrigation vs. rain discrimination, causal tests
├── MODULE_ALERTES/      # 15 agronomic risk alerts, multi-sensor confidence & cascade engine
├── parcelles_geojson/   # GeoJSON spatial boundaries (Makthar, Sidi Mechreg, unified)
├── outputs/             # Spatial databases, clean GeoParquets, rasters, and reports
├── logs/                # Execution logs
└── requirements.txt     # Python runtime dependencies
```

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://gitlab.com/wallah-we-can-group/AWAM-project.git
cd AWAM-project

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the End-to-End Master Pipeline

```bash
python PIPELINE_MASTER/run_master_pipeline.py
```

### 3. Run Individual Modules

- **Data Extraction & Cleaning**:
  ```bash
  python EXTRACT/run_all_extractions.py
  ```
- **VARI Ground-to-Satellite Calibration**:
  ```bash
  python VARI_CALIBRATION/run_vari_pipeline.py
  ```
- **Plant Health Diagnostic**:
  ```bash
  python SANTE_PLANTES/run_health_analysis.py
  ```
- **Irrigation & Water Stress Detection**:
  ```bash
  python IRRIGATION/run_irrigation_analysis.py
  ```
- **Agronomic Alert Engine**:
  ```bash
  python MODULE_ALERTES/run_alertes_pipeline.py
  ```

---

## 🧪 Automated Testing

Execute the complete regression and verification test suite:

```bash
pytest -v
```
