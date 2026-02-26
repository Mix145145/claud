"""Entry point for `python -m tuposcan`."""
import sys

from .config.manager import ConfigManager
from .engine.core import TuposcanEngine
from .utils.logging import setup_logging


def main():
    setup_logging()
    cm = ConfigManager("config/tuposcan_config.json")
    engine = TuposcanEngine(cm)
    engine.initialize()
    print(f"Tuposcan engine initialized (camera={engine._camera.backend_name}, "
          f"serial={engine._serial.connection_name})")
    print("Use tuposcan_gui or tuposcan_web for interactive access.")
    engine.shutdown()


if __name__ == "__main__":
    main()
