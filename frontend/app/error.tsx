"use client";
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <main className="empty-state">
      <h1>The workspace hit an error.</h1>
      <p>{error.message}</p>
      <button className="button" onClick={reset}>
        Try again
      </button>
    </main>
  );
}
