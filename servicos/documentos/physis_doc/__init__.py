"""Serviço de documentos da Physis: ODT/ODS -> PDF/A-2b (LibreOffice) e validação PDF/A (veraPDF).

Roda como serviço separado (outro processo/contêiner): o hub só fala HTTP com ele. O veraPDF (GPLv3+/MPLv2+)
e o LibreOffice (MPL-2.0) não são ligados ao código do hub.
"""
__version__ = "0.1.0"
