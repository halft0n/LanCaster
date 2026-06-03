"""Entry point for PyInstaller-bundled desktop app."""

from lancaster.desktop import DesktopApp


def main():
    app = DesktopApp()
    app.run()


if __name__ == "__main__":
    main()
