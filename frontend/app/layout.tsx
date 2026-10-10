import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
const dmSans = localFont({
  src: "../public/fonts/dmsans.woff2",
  weight: "400 700",
  display: "swap",
  variable: "--font-dm-sans",
});
const spaceGrotesk = localFont({
  src: "../public/fonts/spacegrotesk.woff2",
  weight: "400 700",
  display: "swap",
  variable: "--font-space-grotesk",
});
const plexMono = localFont({
  src: [
    { path: "../public/fonts/ibmplexmono-400.woff2", weight: "400" },
    { path: "../public/fonts/ibmplexmono-500.woff2", weight: "500" },
  ],
  display: "swap",
  variable: "--font-plex-mono",
});
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
    <html
      lang="en"
      className={`${dmSans.variable} ${spaceGrotesk.variable} ${plexMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
