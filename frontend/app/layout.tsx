import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "Sentinel · Personal intelligence", description: "Stay ahead of the changes that matter. Your intelligence, sources, and next steps in one place." };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body className="min-h-screen antialiased">{children}</body></html>;
}
