import type { Metadata } from "next";
import "./globals.css";
import "./analysis.css";
import "./a11y.css";
import "./polish.css";
import "./proof.css";
import "./responsive.css";
import "./inspector.css";
import "./challenge.css";
import "./launcher.css";
import "./selection.css";

export const metadata: Metadata = {
  title: "Prism — Agent execution stories",
  description: "A visual debugger for AI agents."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
