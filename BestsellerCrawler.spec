# PyInstaller one-folder build. Run through build.bat.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("playwright")
hiddenimports += ["PyQt6.QtNetwork", "xlsxwriter"]


def _drop_bundled_browsers(entries):
    """Playwright ships downloaded browsers inside its package (~650MB).

    The app downloads Chromium into %LOCALAPPDATA%\\ms-playwright on first run
    (app/browser_setup.py), so bundling them only bloats the release.
    """
    skip = (".local-browsers", "driver\\package\\types", "driver/package/types")
    return [item for item in entries if not any(part in item[0] or part in str(item[1]) for part in skip)]


datas = _drop_bundled_browsers(datas)
binaries = _drop_bundled_browsers(binaries)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PyQt6.QtWebEngineCore", "PyQt6.Qt3DCore"],
    noarchive=False,
)

# playwright's own PyInstaller hook re-adds the whole driver tree, so filter after Analysis too
a.datas = _drop_bundled_browsers(a.datas)
a.binaries = _drop_bundled_browsers(a.binaries)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BestsellerCrawler",
    console=False,
    icon="app_icon.ico",
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="BestsellerCrawler",
)
