from __future__ import annotations

from psidata import Candidate, detect, read
from psidata.readers.uvvis_text import UVVisMetadata
from psidata.readers.xrd_text import XRDMetadata, XRDTextReader

# --- XRD ---------------------------------------------------------------------------------------
_XY = "3.00 100.0\n3.05 120.0\n3.10 90.0\n3.15 140.0\n"

_PANALYTICAL_CSV = (
    "[Measurement conditions]\n"
    "Sample identification,Silver Behenate\n"
    "Anode material,Cu\n"
    "K-Alpha1 wavelength,1.5405980\n"
    "Scan range,3.000000,60.000000\n"
    "No. of points,3\n"
    "[Scan points]\n"
    "Angle, TimePerStep, Intensity, ESD\n"
    "3.000, 18.0, 100.0, 10.0\n"
    "3.050, 18.0, 250.0, 15.0\n"
    "3.100, 18.0, 90.0, 9.0\n"
)


def _cand(name: str, text: str, hint: str | None) -> Candidate:
    return Candidate(filename=name, text=text, technique_hint=hint, uri=f"https://x/{name}")


def test_xrd_bare_xy_table():
    ds = read(_cand("pattern.xy", _XY, "XRD"))
    assert ds.technique == "XRD"
    sig = ds.signals[0]
    assert sig.x.label == "2θ" and sig.x.unit == "°"
    assert sig.y.label == "Intensity"
    assert list(sig.frame["2θ"]) == [3.00, 3.05, 3.10, 3.15]
    assert list(sig.frame["Intensity"]) == [100.0, 120.0, 90.0, 140.0]


def test_xrd_panalytical_csv_picks_intensity_column_and_metadata():
    ds = read(_cand("pXRD_AgBeh.csv", _PANALYTICAL_CSV, "XRD"))
    assert ds.source.reader == "xrd_text"
    sig = ds.signals[0]
    # 4 columns (Angle, TimePerStep, Intensity, ESD) -> intensity is column index 2, not 1
    assert list(sig.frame["Intensity"]) == [100.0, 250.0, 90.0]
    m = ds.metadata
    assert isinstance(m, XRDMetadata)
    assert m.sample_name == "Silver Behenate"
    assert m.anode == "Cu"
    assert abs(m.wavelength_angstrom - 1.5405980) < 1e-6
    assert m.two_theta_start == 3.0 and m.two_theta_end == 60.0


def test_xrd_needs_the_folder_hint():
    # a bare 2-column table without an XRD hint isn't claimed as XRD
    assert XRDTextReader().sniff(_cand("mystery.xy", _XY, None)) == 0.0


# --- UV-Vis ------------------------------------------------------------------------------------
_UV_TXT = "498.75,0.0041\n499.00,0.0035\n499.25,0.0039\n"

_THORLABS_CSV = (
    "#Thorlabs FTS\n[SpectrumHeader]\n"
    "#InstrModel,CCS175\n#XAxisUnit,nm_air\n#YAxisUnit,absorbance\n"
    "#IntegrationTime,10.000000\n#Type,absorption\n"
    "500.0,0.10\n501.0,0.22\n502.0,0.15\n"
)


def test_uvvis_bare_txt_table():
    ds = read(_cand("iodine.txt", _UV_TXT, "UV-Vis"))
    assert ds.technique == "UV-Vis"
    sig = ds.signals[0]
    assert sig.x.label == "Wavelength" and sig.x.unit == "nm"
    assert list(sig.frame["Wavelength"]) == [498.75, 499.00, 499.25]


def test_uvvis_thorlabs_csv_header_and_absorbance():
    ds = read(_cand("ne.csv", _THORLABS_CSV, "UV-Vis"))
    assert ds.source.reader == "uvvis_text"
    sig = ds.signals[0]
    assert sig.y.label == "Absorbance" and sig.y.quantity == "absorbance"
    assert list(sig.frame["Absorbance"]) == [0.10, 0.22, 0.15]
    m = ds.metadata
    assert isinstance(m, UVVisMetadata)
    assert m.instrument == "CCS175"
    assert m.measurement_type == "absorption"
    assert m.integration_time_ms == 10.0


def test_uvvis_thorlabs_csv_detected_without_hint():
    # the Thorlabs markers are UV-specific enough to detect even without a folder hint
    assert detect(_cand("ne.csv", _THORLABS_CSV, None)).name == "uvvis_text"


# --- XRD structured (PANalytical .xrdml / Philips .udf) ----------------------------------------
_XRDML = (
    '<?xml version="1.0"?>\n'
    '<xrdMeasurements xmlns="http://www.xrdml.com/XRDMeasurement/2.3">\n'
    "  <sample><id>TestSample</id></sample>\n"
    "  <xrdMeasurement>\n"
    '    <usedWavelength><kAlpha1 unit="Angstrom">1.5405980</kAlpha1></usedWavelength>\n'
    "    <incidentBeamPath><xRayTube><anodeMaterial>Cu</anodeMaterial></xRayTube></incidentBeamPath>\n"
    "    <scan><dataPoints>\n"
    '      <positions axis="2Theta" unit="deg"><startPosition>10.0</startPosition>'
    "<endPosition>40.0</endPosition></positions>\n"
    '      <counts unit="counts">100 200 150 400</counts>\n'
    "    </dataPoints></scan>\n"
    "  </xrdMeasurement>\n</xrdMeasurements>\n"
)

_UDF = (
    "SampleIdent,TestUDF,/\nAnode,Cu,/\nLabdaAlpha1, 1.540598,/\n"
    "DataAngleRange,   10.00000,  40.00000,/\nScanStepSize, 10.00000,/\n"
    "ScanType,CONTINUOUS,/\nRawScan\n   100,   200,   150,   400\n"
)


def test_xrd_xrdml():
    ds = read(_cand("AgBeh.xrdml", _XRDML, "XRD"))
    assert ds.source.reader == "xrd_panalytical" and ds.technique == "XRD"
    sig = ds.signals[0]
    assert list(sig.frame["2θ"]) == [10.0, 20.0, 30.0, 40.0]
    assert list(sig.frame["Intensity"]) == [100.0, 200.0, 150.0, 400.0]
    assert ds.metadata.sample_name == "TestSample"
    assert ds.metadata.anode == "Cu"
    assert abs(ds.metadata.wavelength_angstrom - 1.5405980) < 1e-6


def test_xrd_udf():
    ds = read(_cand("AgBeh.udf", _UDF, "XRD"))
    assert ds.source.reader == "xrd_panalytical"
    sig = ds.signals[0]
    assert list(sig.frame["2θ"]) == [10.0, 20.0, 30.0, 40.0]
    assert list(sig.frame["Intensity"]) == [100.0, 200.0, 150.0, 400.0]
    assert ds.metadata.sample_name == "TestUDF" and ds.metadata.anode == "Cu"
