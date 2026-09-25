# 주식 전략 연구실
국내 주식 예측·백테스트로 클라우드 병렬 처리의 성능과 비용을 연구합니다.

## 시작
Python 3.12+, Node 20+ 권장. Windows PowerShell:
```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m lab.cli demo
.venv/Scripts/python.exe -m lab.cli serve
```
다른 터미널:
```powershell
cd web
npm ci
npm run dev
```
http://127.0.0.1:5173 에서 사용합니다.
1. 홈에서 종목명이나 코드를 검색해 선택합니다.
2. **과거 백테스트**: 기간(1년·2년·5년·전체·직접)과 전략을 고르고 실행하면, 계산이 끝나는 즉시 수익 요약·매수/매도 차트·매매 기록이 나타납니다.
3. **미래 예측**: 5·20·60거래일을 고르면 다음을 보여줍니다.
   - 중앙 예측(점선)과 50%·80% 예측 범위(부채꼴), 오를 확률·±10% 확률
   - 예측 근거: 어떤 지표가 오르는 쪽·내리는 쪽으로 밀었는지 막대로 분해(합계 = 중앙 예측)
   - 비슷한 과거 차트: 최근 60거래일 흐름과 가장 비슷했던 과거 5구간과 그 이후 실제 흐름(시나리오 선)
   - 최근 2년 검증: 방향 적중률, '가격 그대로' 대비 오차, 80% 범위 적중률, 시나리오 방향 적중률
4. 차트는 캔들·OHLC 막대·선·영역으로 바꿔 볼 수 있고, 5·20·60·120일 이동평균선을 겹쳐 볼 수 있습니다.

토스 키가 있으면 코스피·코스닥 전체 종목을 검색하고, 처음 여는 종목의 일봉(최대 15페이지, 약 5초)을 자동으로 받습니다. 키는 둘 중 한 방법으로 전달합니다.
- 프로젝트 폴더의 `.env`(git·Docker 제외 대상)에 `TOSS_CLIENT_ID=tsck_live_…`, `TOSS_CLIENT_SECRET=tssk_live_…`를 적어 두면 `serve`가 읽습니다.
- `.env`가 없으면 `serve`가 두 값을 입력받습니다(저장하지 않음). Enter로 건너뛰면 저장된 종목만 검색합니다.

미래 예측 날짜와 차트는 주말과 한국거래소 휴장일(`holidays` 라이브러리의 XKRX 달력)을 제외합니다. 2014~2026년 삼성전자 데이터에서 거래가 없던 평일 189일과 일치함을 확인했습니다.
가상 데이터(`demo`)는 실제 주가가 아닙니다. 계산·UI 검증용입니다.

## 실제 데이터
TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 환경 변수를 로컬에 설정합니다. 키를 파일·채팅·프론트엔드에 넣지 마세요.
```powershell
.venv/Scripts/python.exe -m lab.cli collect-toss 005930 --pages 1
.venv/Scripts/python.exe -m lab.cli import-csv path/to/validated.csv path/to/metadata.json
```
토스 원본 수집 후 스키마와 수정·배당 처리 기준을 검증해야 합니다. examples/dataset-metadata.json의 unknown은 실제 확인 내용으로 변경해야 등록됩니다. 아직 관측하지 않은 토스 응답의 자동 정제는 구현하지 않았습니다.

## 테스트와 빌드
```powershell
.venv/Scripts/python.exe -m pytest -q
cd web
npm run build
```
공개 사이트에는 완료된 실제 데이터이며 표시 권한이 확인된 결과만 내보냅니다.
```powershell
.venv/Scripts/python.exe -m lab.cli export web/public/results
cd web
npm run build:public
```
web/dist가 공개 배포 산출물입니다. 공개 모드에는 백엔드가 필요 없습니다.
CSV 다운로드는 로컬에서도 가능하지만 가상 결과는 SYNTHETIC 파일명으로 구별합니다.

## 문서
- [PRD](docs/PRD.md)
- [기술 설계](docs/ARCHITECTURE.md)
- [디자인 시스템](DESIGN.md)
- [데이터와 모델](docs/DATA-MODEL.md)
- [실험 계획](docs/EXPERIMENTS.md)
- [로드맵](docs/ROADMAP.md)
- [AWS 준비](infra/README.md)

## 현재 제한
AWS 미배포·미측정. 미래 예측은 Ridge 회귀의 통계적 추정입니다. 라이브러리 배포 이후 새로 지정된 임시공휴일은 `holidays`를 갱신해야 반영됩니다. 분할·배당 자체 원장 처리는 없으며 일관된 조정 데이터가 필요합니다.
연구 가정과 데이터 권한을 확인하지 않은 결과를 실제 투자 성과나 공개 자료로 사용하지 않습니다.

## 토스 키 발급 후 첫 연결 확인
PowerShell에서 프로젝트 폴더로 이동하고 아래 명령을 실행합니다.
```powershell
cd 'C:\dev2\cloud project'
.venv\Scripts\python.exe -m lab.cli connect-toss
```
Client ID와 Client Secret을 차례로 붙여넣고 Enter를 누릅니다. 입력 문자는 표시되지 않습니다.
인증 정보는 조회 동안 프로세스 메모리에서만 사용하며 파일에 저장하지 않습니다.
삼성전자 일봉을 최대 20페이지 조회하고, 시각별 data/raw/toss-* 폴더에 원본 응답만 저장합니다.
페이지당 개수·장기 기간은 응답으로 확인해야 하며, 등록된 투자 데이터로 자동 전환하지 않습니다.
성공 시 output 경로와 안내가 표시됩니다. 채팅에는 키를 보내지 말고 완료 여부 또는 오류 메시지만 알려주세요.

### 실제 종목과 거래 차트

실험 실행에서 삼성전자·SK하이닉스·NAVER를 선택할 수 있습니다. 로컬 토스 일봉 스냅샷으로 계산하며, 실험 완료 후 분석 보기에서 캔들·OHLC 막대·종가 선과 거래량을 확인합니다. ▲ 매수 / ▼ 매도 표시의 툴팁과 거래 내역의 위치 보기로 체결 날짜·가격·수량·비용을 확인할 수 있습니다. 구현·검증·데이터 한계는 [실제 종목 및 차트](docs/REAL-DATA-CHARTS.md)를 참조하세요.
