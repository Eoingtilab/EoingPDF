"""EoingPDF desktop entry point."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--convert-child':
        from eoingpdf.convert import native_child
        sys.exit(native_child(*sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] in ('--install-menu', '--uninstall-menu'):
        from eoingpdf.shell import install, uninstall
        (install if sys.argv[1] == '--install-menu' else uninstall)()
        if sys.argv[1] == '--install-menu':
            from eoingpdf.shell import open_default_settings
            open_default_settings()
    elif len(sys.argv) > 1 and sys.argv[1] == '--quick':
        from eoingpdf.quick import main
        main()
    else:
        from eoingpdf.app import main
        main()
