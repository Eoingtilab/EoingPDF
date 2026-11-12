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

본 프로젝트의 소스와 버전 태그는 `Eoingtilab/EoingPDF`, 공식 실행파일은 `Eoingtilab/nalapps-releases`에서 공개 배포한다. 배포 패키지에 프로젝트 LICENSE와 구성요소 고지를 포함하며, 선택한 구성요소 라이선스에 따른 소스 제공·고지 조건을 계속 관리한다.

- 로컬 검색 모델: sentence-transformers/static-similarity-mrl-multilingual-v1, Apache-2.0. 고정 리비전 b68f4122911bcffcd6e1f695f2d99cd6788972d8. 256차원 및 토큰별 int8로 변환했으며 원본 모델 카드, Apache 라이선스 전문, 변경 고지와 해시를 assets/search에 포함한다.
  https://huggingface.co/sentence-transformers/static-similarity-mrl-multilingual-v1
- ONNX Runtime 및 tokenizers는 검색 프로세스에서만 사용한다. 배포 메타데이터와 ONNX Runtime 패키지 고지를 패키징한다. 전체 의존성의 배포 고지 검토는 최종 배포 검사에 포함한다.

## 향후 독점 프리웨어 전환 검토 (2026-11-12)

현재 라이선스를 변경한 것이 아니다. 기존 AGPL 배포본의 권리는 그대로 유지하며, 다음 확인이 끝나기 전에는 독점 라이선스를 적용하지 않는다.

- Git 이력의 작성자 표시는 `Eoingti Lab`, `Eoingti Lab Inc.` 두 항목이지만, 이 표기만으로 전체 코드·기여물의 저작권 또는 양도 여부를 증명할 수 없다. 원저작물, 외주 계약, 외부 기여물 및 사용 허락을 별도 확인한다.
- PyMuPDF/MuPDF는 AGPL 조건을 따르거나 적절한 상용 라이선스를 확보해야 한다. 상용 비용은 제품 및 배포 조건에 따른 견적 확인이 필요하다. 대안은 AGPL 준수를 계속하거나, 필요한 PDF 기능을 다른 적법한 구성요소로 대체하는 것이다. https://pymupdf.io/licensing
- PySide6/Qt는 사용한 각 모듈과 배포 방식에 따라 LGPL, GPL 또는 상용 조건을 확인해야 한다. LGPL 사용 시 고지, 해당 소스 제공과 이용자의 라이브러리 교체 가능성 등을 확인하며, Store 패키지에도 제한이 없는지 별도 검토한다. 상용 계약이 항상 필수인 것은 아니며 비용은 공급사 견적이 필요하다. https://doc.qt.io/qtforpython-6/licenses.html
- Pretendard, Pillow, pywin32, OpenCV, NumPy, ONNX Runtime, tokenizers, 검색 모델과 이들의 포함 구성요소도 실제 배포물 기준으로 고지·라이선스 전문·소스 제공 의무를 확인한다. 현재 목록은 완전한 법률 감사 결과가 아니며 누락 가능성이 있다.
- 위 검토는 법률 의견이나 권리 확보의 완료를 의미하지 않는다. 전환 전 권리자와 라이선스 전문가의 확인이 필요하다.
