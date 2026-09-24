# AWS 실행 준비
이 템플릿은 아직 배포하지 않았다. 실제 계정·네트워크·이미지 준비와 AWS 검증이 필요하다.

## 준비
1. ap-northeast-2에 연구용 ECR 저장소를 생성한다.
2. Dockerfile로 linux/amd64 이미지를 빌드하고 ECR에 푸시한다. 실험에는 digest URI를 사용한다.
3. 인터넷 게이트웨이 경로가 있는 public subnet과 VPC를 준비한다. NAT Gateway는 이 기본 구성에 사용하지 않는다.
4. AWS CLI로 cloudformation validate-template을 수행한 뒤 cloudformation.json을 배포한다.
5. VpcId, PublicSubnets, ImageUri, BudgetEmail을 전달하며 IAM 생성에는 CAPABILITY_IAM이 필요하다.
6. AWS Batch 서비스 연결 역할이 없는 계정은 생성 권한이 필요하다.

## 구성과 비용
작업자 1vCPU/2GB, 최대 4vCPU, 기본 600초. 공인 IP가 있지만 인바운드 규칙은 없다.
S3 작업 역할은 연구 버킷의 experiments/*만 접근한다. 사이트 버킷은 CloudFront만 읽는다.
월 예산 기본 15 USD는 환율·세금에 따라 원화 3만 원과 다르다. 실제 환율과 여유 비용을 반영해 설정한다.
Budgets는 알림이며 자동 차단이 아니다. ECR 저장·IPv4·전송·CloudFront 등 별도 요금 확인.
연구용 버킷은 스택 삭제 시 보존된다. 비용 종료 시 보존 버킷·ECR 잔여물을 별도로 검토한다.

## 명시적 실험 명령
```powershell
python -m lab.cloud experiment --manifest examples/manifest.json --bucket BUCKET --queue QUEUE --definition JOB_DEFINITION --workers 1 --timeout 600
```
같은 manifest로 --workers 2, 4를 반복한다. 실제 측정은 data/benchmarks에 기록.
중단·시간 초과 시 제출된 작업을 종료한다. 네트워크 단절 시 콘솔에서 잔여 작업 상태를 확인한다.

## 정적 사이트
로컬 export 명령 → web에서 npm run build:public → web/dist의 파일만 SiteBucket으로 업로드.
데이터 이용 조건 확인 전 공개 결과는 빈 목록이어야 한다.
S3 원본 데이터 버킷이나 로컬 data 폴더를 사이트 버킷에 업로드하지 않는다.
