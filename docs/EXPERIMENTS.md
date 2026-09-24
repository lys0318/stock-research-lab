# 실험 계획과 기록

## 가설
작업 증가 시 병렬화가 전체 완료 시간을 줄이는지, 시작·대기·저장 비용이 이득을 상쇄하는 구간이 있는지 검증한다.
로컬 성능을 AWS 성능으로 표시하지 않는다. 예측 정확도 향상을 클라우드 효과로 해석하지 않는다.

## 통제
동일 데이터 버전, 코드·컨테이너 digest, seed, 입력 작업 목록, 작업자별 1vCPU/2GB, 수치 라이브러리 스레드 1.
동시 실행 목표 1·2·4. 작업 10·100·1000 후보. 동일 manifest를 반복 사용.
예비 실험에서 작업 묶음 크기를 정하고 본 실험 도중 변경하지 않는다.
조건별 반복 3회. 예산 때문에 축소 시 실제 조건을 보고서에 기재한다.

## 로컬
python -m lab.benchmark examples/manifest.json --workers 1 2 4 --repeats 3
예시 dataset_id를 실제 로컬 버전으로 교체한다.
동일 입력별 metrics/curve를 비교하고 불일치 시 실험 실패. 기록은 data/benchmarks.

## AWS
infra/README.md의 스택·이미지 준비 후 python -m lab.cloud experiment를 명시적으로 실행한다.
각 작업의 Batch createdAt/startedAt/stoppedAt과 내부 계산 시작·종료를 저장.
클라이언트 전체 시간에는 S3 결과 수신도 포함되므로 보고서에서 경계를 명시한다.
관측 동시성은 내부 계산 구간 중첩이며 Fargate 자원 할당 시간과 동일하지 않다.
AWS 결과의 동등성은 비교 전 null이며 검증되지 않은 상태를 true로 표시하지 않는다.

## 비용
작업당 비용=(해당 실행의 계산 사용료)/완료 작업 수.
Fargate 청구 시간은 내부 Python 계산 시간과 다르다. 현재 프로그램은 비용 값을 null로 기록하며 임의 단가를 사용하지 않는다.
이미지 다운로드·최소 청구 단위·S3·ECR·CloudWatch·CloudFront 및 세금을 별도로 반영한다.
ap-northeast-2의 실험일 단가와 실제 청구 자료를 보관한 뒤 산정한다.
목표 월 3만 원. 알림은 강제 차단이 아니다. 예비 작업 1개부터 시작, timeout 기본 600초·최대 1800초, max vCPU 4.
상시 서버 비용과 비교하는 값은 실측 절감액이 아니라 동일 관찰 기간의 비용 모델로 명시한다.

## 장애와 통계
실패한 실험은 성공 시간 통계에서 제외하되 실패 수를 별도 보고. 실패 결과도 삭제하지 않는다.
취소 후 잔여 AWS 작업 확인. 수집 및 실행 시각, 이미지 버전, 로그를 보관한다.
완료 시간 평균·최솟값·최댓값, 관측 동시성, 처리량과 비용을 제시한다.

AWS 비교: python -m lab.report compare data/benchmarks/A.json data/benchmarks/B.json
CSV 요약: python -m lab.report csv data/benchmarks/A.json --output summary.csv
