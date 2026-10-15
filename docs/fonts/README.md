# docs/fonts

- 출처: NanumGothic-Regular.ttf, Google Fonts 저장소 `ofl/nanumgothic` (https://github.com/google/fonts/tree/main/ofl/nanumgothic), 2026-10-15 내려받음. 저작권 (c) 2010 NHN Corporation.
- 라이선스: SIL Open Font License 1.1 (같은 폴더의 OFL.txt). 재배포·동봉 허용, 폰트 자체 판매 금지, 예약 글꼴명(Nanum 계열) 유지.
- 용도: `_fonts.setup_korean_font()` 가 이 파일을 matplotlib 에 등록해 한글 폰트가 없는 환경(CI, 리눅스 서버)에서도 PDF·PNG 의 한글이 깨지지 않게 한다. Regular 한 벌만 동봉하며(약 2.0 MB), bold 는 같은 글리프로 그려진다.
