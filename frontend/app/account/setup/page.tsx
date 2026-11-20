"use client";

import { useRouter } from "next/navigation";
import ProfileForm from "@/components/ProfileForm";
import { useSession } from "@/components/Session";
import { homeFor } from "@/lib/crm";

export default function ProfileSetupPage() {
  const router = useRouter();
  const { identity } = useSession();
  return identity && <ProfileForm onDone={() => router.replace(homeFor(identity))} />;
}