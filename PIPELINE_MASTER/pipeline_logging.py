#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline_logging.py
===================================================================
Gestionnaire unifié de journalisation (logging) pour GeoAI AWAM.

Fournit des loggers professionnels configurés pour :
1. La sortie console (stdout) propre.
2. La persistance structurée dans scripts/logs/pipeline_master.log
   avec ROTATION automatique (10 Mo max, 5 fichiers de backup).
   BUGFIX §27.6.B.2 : l'ancien FileHandler laissait le fichier croître
   indéfiniment, saturant progressivement le disque serveur.
"""

import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from config_global import LOGS_DIR
except ImportError:
    LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
MASTER_LOG_FILE = LOGS_DIR / "pipeline_master.log"


def get_logger(name: str = "AWAM.Master", level: int = logging.INFO) -> logging.Logger:
    """
    Retourne un Logger configuré avec handlers Console et Fichier rotatif.
    Évite les handlers en double si déjà configuré.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 1. Console Handler
        c_handler = logging.StreamHandler(sys.stdout)
        c_handler.setLevel(level)
        c_handler.setFormatter(formatter)
        logger.addHandler(c_handler)

        # 2. BUGFIX §27.6.B.2 : RotatingFileHandler (max 10 Mo, 5 fichiers backup)
        # L'ancien FileHandler laissait le log croître indéfiniment.
        f_handler = RotatingFileHandler(
            MASTER_LOG_FILE,
            encoding="utf-8",
            maxBytes=10 * 1024 * 1024,  # 10 Mo
            backupCount=5
        )
        f_handler.setLevel(level)
        f_handler.setFormatter(formatter)
        logger.addHandler(f_handler)

    return logger


if __name__ == "__main__":
    log = get_logger("AWAM.Test")
    log.info("Test du logger unifié GeoAI AWAM depuis PIPELINE_MASTER OK.")
    print(f"✓ Fichier de log vérifié : {MASTER_LOG_FILE}")
