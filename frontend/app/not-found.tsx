import Link from "next/link";
export default function NotFound() {
  return (
    <main className="empty-state">
      <h1>Page not found.</h1>
      <Link className="button" href="/workspace">
        Open workspace
      </Link>
    </main>
  );
}
