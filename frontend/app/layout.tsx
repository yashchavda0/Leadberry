import type { Metadata } from "next";
import SessionProvider from "@/components/Session";
import "./globals.css";

export const metadata: Metadata = {
  title: "LeadBerry CRM",
  description: "Organization CRM with secure lead and role management",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
