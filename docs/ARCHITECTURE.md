# 기술 설계

## 실행 경로
React/Vite(127.0.0.1:5173) → 개발 프록시 → FastAPI(127.0.0.1:8000) → 별도 Python 프로세스.
SQLite: 설정·상태·시도 번호. Parquet: 검증된 OHLCV. JSON: 결과. CSV: 화면에서 자산 곡선 내보내기.
동시 로컬 작업 2개. 재시작 시 중단된 작업은 실패로 전환. 자동 재제출하지 않는다.
완료 결과는 임시 파일을 원자적으로 교체한 뒤 상태를 완료로 전환한다. 취소된 상태는 완료로 덮어쓰지 않는다.

## 로컬 API
GET /api/datasets, GET /api/runs, POST /api/runs,
GET /api/runs/{id}, POST /api/runs/{id}/cancel, GET /api/runs/{id}/results.
POST는 X-Research-Local: 1 필요. 허용 Host/Origin을 제한한다. 이 헤더는 로그인 수단이 아니며 루프백 바인딩이 필수다.
입력: dataset_id, start/end, strategy(hold/ma/model), capital, fee, tax, slippage, ma_window, seed.
상태: queued→running→completed/failed/cancelled. 결과는 완료 상태에서만 조회 가능.
API에 AWS 실행 엔드포인트를 두지 않는다. AWS 작업은 연구자 CLI가 제출·감시·종료한다.

## 공개 배포
Vite public 모드 → S3 비공개 사이트 버킷 → CloudFront OAC.
공개 웹은 /results/index.json만 읽는다. 실행 탭은 제외한다. 로컬 API 키·원본 데이터·SQLite는 빌드에 포함하지 않는다.
내보내기는 synthetic=false AND publication_allowed=true AND completed를 모두 요구한다.
이 권한 플래그는 이용허가를 자동 판단하는 기능이 아니며 연구자가 확인 후 메타데이터에 설정해야 한다.

## AWS
S3에 데이터 버전·작업 manifest 업로드, ECR 컨테이너를 Batch Fargate로 실행.
작업은 입력 목록을 1/2/4 그룹으로 나눠 동일한 계산 함수를 사용한다.
Fargate가 목표 동시성 그대로 동작한다고 가정하지 않는다. 작업·계산 시각을 기록해 실제 중첩을 측정한다.
진행 중 실패·시간 초과·중단 시 제출한 작업을 종료한다. 결과 재제출은 새 experiment ID로 보관한다.

## 버전·재현성
데이터 버전은 정제 CSV 내용과 출처·조정 메타데이터 해시.
결과에 계산 코드 해시·설정·seed·Python 및 플랫폼을 기록한다.
의존성 잠금 파일과 ECR 이미지 digest를 실험 기록에 함께 보관한다.
리전 ap-northeast-2, CPU 단일 스레드 환경을 기본으로 한다.
