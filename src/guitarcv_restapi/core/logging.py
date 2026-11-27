import copy
import logging.config


_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "detailed",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": "app.log",
            "encoding": "utf-8",
            "level": "DEBUG",
            "formatter": "detailed",
        },
    },
    # Module-level loggers `logging.getLogger(__name__)`
    "root": {
        "handlers": ["console", "file"],
        "level": "DEBUG",
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": [],
            "level": "INFO",
            "propagate": True,
        },
        "uvicorn.access": {
            "handlers": [],
            "level": "INFO",
            "propagate": True,
        },
    },
}


def setup() -> None:
    from guitarcv_restapi.core.config import settings

    settings.log_dir.mkdir(parents=True, exist_ok=True)

    configuration = copy.deepcopy(_LOGGING_CONFIG)
    configuration["handlers"]["file"]["filename"] = str(
        settings.log_dir / "app.log"
    )
    configuration["handlers"]["console"]["level"] = (
        "DEBUG" if settings.debug else "INFO"
    )
    logging.config.dictConfig(configuration)
