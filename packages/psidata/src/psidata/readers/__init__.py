"""Built-in readers. Importing a reader module registers it via ``@register_reader``.

To add a technique, create a module here (e.g. ``ftir_jcamp.py``) and import it below.
"""

from __future__ import annotations

from . import (
    acoustic_spectrum,  # noqa: F401  (import triggers registration)
    agilent_dad,  # noqa: F401  (import triggers registration)
    brillouin_asc,  # noqa: F401  (import triggers registration)
    cd_dcs,  # noqa: F401  (import triggers registration)
    comp_input,  # noqa: F401  (import triggers registration)
    comp_log,  # noqa: F401  (import triggers registration)
    comp_spectrum,  # noqa: F401  (import triggers registration)
    dielectric_text,  # noqa: F401  (import triggers registration)
    dm3_image,  # noqa: F401  (import triggers registration)
    dsc_trios,  # noqa: F401  (import triggers registration)
    ftir_jcamp,  # noqa: F401  (import triggers registration)
    ftir_opus,  # noqa: F401  (import triggers registration)
    ftir_pe_asc,  # noqa: F401  (import triggers registration)
    ftir_text,  # noqa: F401  (import triggers registration)
    gamry_dta,  # noqa: F401  (import triggers registration)
    hplc_text,  # noqa: F401  (import triggers registration)
    jcamp_electrochem,  # noqa: F401  (import triggers registration)
    jcamp_ms,  # noqa: F401  (import triggers registration)
    microscopy_image,  # noqa: F401  (import triggers registration)
    nmr_2d_jcamp,  # noqa: F401  (import triggers registration)
    nmr_jcamp,  # noqa: F401  (import triggers registration)
    nmr_text,  # noqa: F401  (import triggers registration)
    nmr_totxt,  # noqa: F401  (import triggers registration)
    raman_text,  # noqa: F401  (import triggers registration)
    spreadsheet_table,  # noqa: F401  (import triggers registration)
    structure_file,  # noqa: F401  (import triggers registration)
    tga_text,  # noqa: F401  (import triggers registration)
    uvvis_text,  # noqa: F401  (import triggers registration)
    wav_audio,  # noqa: F401  (import triggers registration)
    xrd_image,  # noqa: F401  (import triggers registration)
    xrd_panalytical,  # noqa: F401  (import triggers registration)
    xrd_text,  # noqa: F401  (import triggers registration)
)

__all__ = ["acoustic_spectrum", "agilent_dad", "brillouin_asc", "comp_input", "comp_log", "cd_dcs", "comp_spectrum", "dielectric_text", "dm3_image", "dsc_trios",
           "ftir_jcamp", "ftir_opus", "ftir_pe_asc", "ftir_text", "gamry_dta", "hplc_text", "jcamp_electrochem", "jcamp_ms",
           "microscopy_image", "nmr_2d_jcamp", "nmr_jcamp", "nmr_text", "nmr_totxt", "raman_text", "spreadsheet_table", "structure_file",
           "tga_text", "uvvis_text", "wav_audio", "xrd_image", "xrd_panalytical", "xrd_text"]
