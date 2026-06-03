"""Entry point for PyInstaller-bundled desktop app."""

import argparse


def main():
    parser = argparse.ArgumentParser(description="LanCaster Desktop")
    parser.add_argument("-p", "--port", type=int, default=8200, help="Web server port")
    parser.add_argument("--debug", action="store_true", help="Enable DevTools")
    args = parser.parse_args()

    from lancaster.desktop import DesktopApp

    app = DesktopApp(port=args.port, debug=args.debug)
    app.run()


if __name__ == "__main__":
    main()
