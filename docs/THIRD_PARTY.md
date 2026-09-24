# 외부 구성요소

- Pretendard: SIL Open Font License 1.1. `assets/fonts/OFL.txt` 포함.
  https://github.com/orioncactus/pretendard
- PySide6 / Qt: LGPLv3 또는 상용 라이선스. 동적 라이브러리로 배포.
  https://doc.qt.io/qtforpython-6/licenses.html
- PyMuPDF / MuPDF: AGPLv3 또는 상용 라이선스.
  https://pymupdf.readthedocs.io/en/latest/about.html
- Pillow: HPND. https://github.com/python-pillow/Pillow
- pywin32: PSF 계열 라이선스. https://github.com/mhammond/pywin32
- OpenCV headless: OpenCV/패키지의 배포 라이선스 및 제3자 고지 확인 대상. https://github.com/opencv/opencv
- NumPy: BSD-3-Clause 및 포함 구성요소 고지. https://numpy.org/doc/stable/license.html
- NalApps Windows SDK: 사용자 소유 공통 테마 원본, 고정 커밋은 `assets/nalapps-sdk/provenance.json` 참조.
- .NET Framework: Windows 제공 런타임. 우클릭 COM 연결 프로그램에 사용.

한글 자동화의 상업적 이용은 한컴의 별도 이용 조건을 확인해야 한다.
https://developer.hancom.com/hwpautomation

현재 배포는 사용자 로컬 검증용이다. 외부 배포 시 선택한 구성요소 라이선스에 맞는 소스 제공과 고지를 함께 구성한다.

- 로컬 검색 모델: sentence-transformers/static-similarity-mrl-multilingual-v1, Apache-2.0. 고정 리비전 b68f4122911bcffcd6e1f695f2d99cd6788972d8. 256차원 및 토큰별 int8로 변환했으며 원본 모델 카드, Apache 라이선스 전문, 변경 고지와 해시를 assets/search에 포함한다.
  https://huggingface.co/sentence-transformers/static-similarity-mrl-multilingual-v1
- ONNX Runtime 및 tokenizers는 검색 프로세스에서만 사용한다. 배포 메타데이터와 ONNX Runtime 패키지 고지를 패키징한다. 전체 의존성의 배포 고지 검토는 최종 배포 검사에 포함한다.
