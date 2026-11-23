import PlatformLayout from "@/components/platform/PlatformLayout";
import "./platform.css";

export default function Layout({ children }: { children: React.ReactNode }) {
  return <PlatformLayout>{children}</PlatformLayout>;
}