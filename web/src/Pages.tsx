import { Cloud as CloudIcon, LineChart } from "lucide-react";
import { api, labels, pct, publicMode, states, tone, type Benchmark, type Dataset, type Job } from "./api";

export function History({ jobs, datasets, onOpen, onChanged, onError }: {
  jobs: Job[]; datasets: Dataset[]; onOpen: (job: Job) => void; onChanged: () => void; onError: (message: string) => void;
}) {
  async function cancel(job: Job) {
    try { await api(`/runs/${job.id}/cancel`, { method: "POST" }); onChanged(); }
    catch (e) { onError((e as Error).message); }
  }
  return <>
    <section className="page-title"><h1>실험 기록</h1><p className="muted">최근 100개 실험입니다. 완료된 실험을 열면 같은 조건으로 다시 실행할 수 있습니다.</p></section>
    {jobs.length ? <div className="table-wrap"><table>
      <thead><tr><th>종목 · 전략</th><th>기간</th><th>상태</th><th>수익률</th><th><span className="sr-only">동작</span></th></tr></thead>
      <tbody>{jobs.map((j) => {
        const d = datasets.find((x) => x.id === j.config.dataset_id);
        return <tr key={j.id}>
          <td><strong>{d?.name ?? "종목"} · {labels[j.config.strategy]}</strong><small>{j.id.slice(0, 10)}{d?.synthetic ? " · 가상 데이터" : ""}</small></td>
          <td>{j.config.start}<small>{j.config.end}</small></td>
          <td><span className={"badge " + j.status}>{states[j.status]}</span>{j.error && <small className="error-text">{j.error}</small>}</td>
          <td className={j.metrics ? tone(j.metrics.total_return) : ""}>{j.metrics ? pct(j.metrics.total_return) : "—"}</td>
          <td>{j.status === "completed" ? <button className="btn btn-secondary btn-sm" onClick={() => onOpen(j)}>열기</button>
            : !publicMode && ["queued", "running"].includes(j.status) ? <button className="btn btn-ghost btn-sm" onClick={() => cancel(j)}>취소</button> : null}</td>
        </tr>;
      })}</tbody>
    </table></div> : <div className="empty"><LineChart size={28} /><h3>아직 실험이 없습니다</h3><p>새 분석에서 종목을 검색해 첫 백테스트를 실행하세요.</p></div>}
  </>;
}

export function Cloud({ reports }: { reports: Benchmark[] }) {
  return <>
    <section className="page-title"><h1>클라우드 실험</h1><p className="muted">같은 계산을 작업자 1·2·4개로 나눠 실행하고 시간과 비용을 비교합니다.</p></section>
    <div className="table-wrap"><table>
      <thead><tr><th>지표</th><th>측정 기준</th></tr></thead>
      <tbody>
        <tr><td>전체 완료 시간</td><td>작업 제출부터 마지막 결과 저장까지</td></tr>
        <tr><td>처리량</td><td>완료한 백테스트 수 / 전체 시간</td></tr>
        <tr><td>실제 동시성</td><td>작업별 실행 시작·종료 시각의 중첩</td></tr>
        <tr><td>계산 비용</td><td>사용량 기반 추정과 실제 청구를 별도 기록</td></tr>
      </tbody>
    </table></div>
    {reports.map((report) => <section className="panel-block" key={report.id}>
      <div className="section-row"><h2>{report.environment === "local" ? "로컬 병렬 실험" : "AWS Fargate 실험"}</h2><span className="caption">{report.created_at.slice(0, 16).replace("T", " ")} · {report.id.slice(0, 10)}</span></div>
      <div className="table-wrap"><table>
        <thead><tr><th>목표 작업자</th><th>관측 동시성</th><th>전체 시간</th><th>처리량</th><th>결과 일치</th></tr></thead>
        <tbody>{report.runs.map((r, i) => <tr key={i}>
          <td>{r.workers}</td><td>{r.observed_concurrency}</td><td>{r.total_seconds.toFixed(3)}초</td><td>{r.throughput.toFixed(2)}작업/초</td>
          <td>{r.equal_results === true ? "확인" : r.equal_results === false ? "불일치" : "비교 전"}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="caption">{report.cost_note}</p>
    </section>)}
    {!reports.some((r) => r.environment === "aws-fargate") && <div className="empty"><CloudIcon size={28} /><h3>AWS 실측 결과를 기다리고 있습니다</h3>
      <p>로컬 측정치를 AWS 성능으로 표시하지 않습니다. 연구용 CLI로 AWS 실험 보고서를 만들 수 있습니다.</p></div>}
  </>;
}

export function DataInfo({ datasets }: { datasets: Dataset[] }) {
  return <>
    <section className="page-title"><h1>데이터 안내</h1><p className="muted">어떤 데이터로, 어떤 가정 아래 분석했는지 확인하세요.</p></section>
    <div className="notice"><strong>{datasets.some((d) => !d.synthetic) ? "토스증권 일봉 스냅샷" : "토스증권 데이터 검증 대기"}</strong>
      <p>저장된 일봉으로 분석하며 실시간 시세가 아닙니다. 수정주가의 분할·배당 세부 기준과 공개 표시 권한은 확인 중이므로 실제 데이터는 로컬 탐색용입니다.</p></div>
    <div className="table-wrap"><table>
      <thead><tr><th>종목 / 공급원</th><th>확보 기간</th><th>조정 기준</th></tr></thead>
      <tbody>{datasets.map((d) => <tr key={d.id}>
        <td><strong>{d.name}</strong><small>{d.symbol} · {d.source}{d.synthetic ? " · 개발용 가상 데이터" : ""}</small></td>
        <td>{d.start}<small>{d.end}</small></td>
        <td className="wrap">{d.adjustment}</td>
      </tr>)}</tbody>
    </table></div>
    <section className="reading">
      <h2>분석의 전제</h2>
      <p>일별 주가로 판단하고 다음 거래일 시가에 체결합니다. 거래 비용은 입력한 모형을 사용하며 실제 세금 계산 서비스가 아닙니다.</p>
      <p>AI 방향 예측은 과거 학습 구간에서만 학습하고, 검증 구간에서 조건을 고른 뒤 최종 평가 구간을 따로 둡니다. 미래 가격 예측도 최근 구간을 학습에서 빼고 검증한 수치를 함께 표시합니다.</p>
      <p>선정한 종목의 결과를 시장 전체로 일반화하지 않습니다.</p>
    </section>
  </>;
}
