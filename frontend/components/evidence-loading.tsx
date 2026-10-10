export function EvidenceLoading({ label }: { label: string }) {
  return (
    <div className="evidence-loading" role="status" aria-label={label}>
      <p>{label}</p>
      <div aria-hidden="true" className="evidence-skeleton">
        <span />
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}
