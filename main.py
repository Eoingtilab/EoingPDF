"""EoingPDF desktop entry point."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--search-child':
        from eoingpdf.search_child import child_main
        sys.exit(child_main())
    elif len(sys.argv) > 1 and sys.argv[1] == '--health-check':
        from eoingpdf.health_check import main
        sys.exit(main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == '--maintenance-child':
        from eoingpdf.update_helper import child_main
        sys.exit(child_main())
    elif len(sys.argv) > 1 and sys.argv[1] == '--transform-child':
        from eoingpdf.transform_process import child_main
        sys.exit(child_main())
    elif len(sys.argv) > 1 and sys.argv[1] == '--sniff-child':
        from eoingpdf.sniffer import main
        sys.exit(main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == '--license':
        from eoingpdf.license_ui import main
        sys.exit(main())
    elif len(sys.argv) > 1 and sys.argv[1] == '--rollback-update':
        from eoingpdf.localization import tr
        from eoingpdf.updates import latest_backup
        from eoingpdf.update_helper import launch
        try:
            backup = latest_backup()
            if backup is None:
                raise ValueError(tr('복원할 전체 백업이 없습니다.'))
            launch(backup[0])
        except Exception as error:
            if sys.stderr is not None:
                print(tr('업데이트 복원 실패: {error}', error=error), file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == '--convert-child':
        from eoingpdf.convert import native_child
        sys.exit(native_child(*sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] in ('--install-menu', '--register-shell', '--uninstall-menu'):
        from eoingpdf.shell_cli import main
        sys.exit(main(sys.argv[1:]))
    elif len(sys.argv) > 1 and sys.argv[1] == '--quick':
        from eoingpdf.quick import main
        main()
    else:
        from eoingpdf.app import main
        main()
