import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "ATLAS — Intersection intelligence",
  description:
    "From traffic footage to a living digital twin. Computer vision, traffic analytics, and reproducible signal optimization.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
